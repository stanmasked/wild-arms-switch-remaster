"""Track executed packed-Q12 *values* through MIPS ALU/HI/LO to matrix SH.

Private raw load/store addresses are consumed in memory; the returned report
contains only fixed matrix-slot numbers, counts and conservative booleans.
This is dynamic dependency (taint), not a numerical PS1 equivalence proof.
"""
from dataclasses import dataclass
import struct

try:
    from .audit_gp0_trig_table import TABLE, ENTRIES
    from .mips_control_flow import LOADS, STORES
except ImportError:
    from audit_gp0_trig_table import TABLE, ENTRIES
    from mips_control_flow import LOADS, STORES


@dataclass(frozen=True)
class Lineage:
    lookups: frozenset = frozenset()
    via_mult: bool = False
    via_hilo: bool = False
    via_spill: bool = False
    external_unresolved: bool = False


def join(*origins):
    return Lineage(
        frozenset().union(*(x.lookups for x in origins)),
        any(x.via_mult for x in origins),
        any(x.via_hilo for x in origins),
        any(x.via_spill for x in origins),
        any(x.external_unresolved for x in origins),
    )


def _alu(word, regs, hi, lo):
    """Return (destination, lineage, next_hi, next_lo) for executed ALU/control."""
    op = word >> 26
    rs, rt, rd, sa, fn = ((word >> 21) & 31, (word >> 16) & 31,
                           (word >> 11) & 31, (word >> 6) & 31, word & 63)
    a, b = regs[rs], regs[rt]
    if word == 0:
        return None, None, hi, lo
    if op == 0:
        if fn == 8:  # JR
            return None, None, hi, lo
        if fn == 9:  # JALR
            return rd, Lineage(), hi, lo
        if fn in (0, 2, 3):
            return rd, b, hi, lo
        if fn in (4, 6, 7):
            return rd, join(a, b), hi, lo
        if fn in (24, 25):  # MULT/MULTU -> HI and LO
            product = join(a, b)
            product = Lineage(product.lookups, bool(product.lookups) or product.via_mult,
                              product.via_hilo, product.via_spill,
                              product.external_unresolved)
            return None, None, product, product
        if fn in (16, 18):  # MFHI/MFLO
            value = hi if fn == 16 else lo
            return rd, Lineage(value.lookups, value.via_mult,
                               bool(value.lookups) or value.via_hilo,
                               value.via_spill, value.external_unresolved), hi, lo
        if fn in (17, 19):  # MTHI/MTLO
            if fn == 17:
                hi = a
            else:
                lo = a
            return None, None, hi, lo
        if fn in (32, 33, 34, 35, 36, 37, 38, 39, 42, 43):
            return rd, join(a, b), hi, lo
        raise ValueError('unsupported executed SPECIAL instruction')
    if op in (8, 9, 10, 11, 12, 13, 14):
        return rt, a, hi, lo
    if op == 15:
        return rt, Lineage(), hi, lo
    if op == 3:  # JAL
        return 31, Lineage(), hi, lo
    if op in (1, 2, 4, 5, 6, 7, 20, 21, 22, 23):
        return None, None, hi, lo
    raise ValueError('unsupported executed opcode for value lineage')


def summarize(image, base, trace, matrix_address, *,
              table_address=TABLE, table_entries=ENTRIES, matrix_slots=9):
    """Follow successful concrete Q12 loads to signed-halfword matrix stores.

    Data-dependence is combined conservatively at ALU operations, so a table
    value that is mathematically cancelled may still be counted as influencing
    a destination. The result deliberately never contains register or matrix
    values, private addresses, lookup indices, or executable instruction bytes.
    """
    if (not isinstance(base, int) or base & 3 or len(image) & 3
            or not isinstance(matrix_address, int) or matrix_address & 1
            or not isinstance(table_address, int) or table_address & 3
            or not isinstance(table_entries, int) or table_entries < 1
            or not isinstance(matrix_slots, int) or not 1 <= matrix_slots <= 128):
        raise ValueError('invalid lineage memory configuration')
    visited = trace['visited_pcs']
    loads = iter(trace['load_accesses'])
    stores = iter(trace['store_addresses'])
    memory_shadow = {}       # per byte, so SH/SW/overlapping loads work
    gpr = [Lineage(external_unresolved=True) for _ in range(32)]
    gpr[0] = Lineage()
    hi = lo = Lineage(external_unresolved=True)
    pending = None           # one-cycle MIPS load delay
    slots = [None] * matrix_slots  # last successfully written SH lineage
    trig_load_count = 0
    trig_reads_contributing = set()
    for pc in visited:
        if (not isinstance(pc, int) or pc < base
                or (pc - base) % 4 or pc + 4 > base + len(image)):
            raise ValueError('executed PC outside executable image')
        word, = struct.unpack_from('<I', image, pc - base)
        op = word >> 26
        rt = (word >> 16) & 31
        dest = None
        new_value = None
        new_pending = None
        if op in LOADS:
            event = next(loads, None)
            if (event is None or len(event) != 4 or event[0] != pc
                    or event[2] != LOADS[op] or event[3] != rt):
                raise ValueError('missing or mismatched executed load event')
            address, width = event[1], event[2]
            if not isinstance(address, int) or address < 0 or address % width:
                raise ValueError('invalid load event address')
            if (op == 35 and table_address <= address
                    and address + 4 <= table_address + 4 * table_entries
                    and (address - table_address) % 4 == 0):
                trig_load_count += 1
                value = Lineage(lookups=frozenset({trig_load_count}))
            else:
                parts = [memory_shadow.get(address + j,
                          Lineage(external_unresolved=True)) for j in range(width)]
                value = join(*parts)
                if value.lookups:
                    value = Lineage(value.lookups, value.via_mult, value.via_hilo,
                                    True, value.external_unresolved)
            new_pending = (rt, value) if rt else None
        elif op in STORES:
            address = next(stores, None)
            width = STORES[op]
            if not isinstance(address, int) or address < 0 or address % width:
                raise ValueError('missing or invalid executed store address')
            # The currently pending LW is not yet visible to this store.
            value = gpr[rt]
            for j in range(width):
                memory_shadow[address + j] = value
            # Any overlapping byte/word store invalidates an older SH-origin
            # assertion for a now-overwritten matrix coefficient. Only a final
            # complete SH to the exact slot establishes its SH lineage.
            for index in range(matrix_slots):
                slot_start = matrix_address + 2 * index
                if address < slot_start + 2 and address + width > slot_start:
                    if op == 41 and address == slot_start:
                        slots[index] = value
                    else:
                        slots[index] = None
        else:
            dest, new_value, hi, lo = _alu(word, gpr, hi, lo)
        if pending is not None and pending[0] != dest:
            gpr[pending[0]] = pending[1]
        if dest:
            gpr[dest] = new_value
        gpr[0] = Lineage()
        pending = new_pending
    if next(loads, None) is not None or next(stores, None) is not None:
        raise ValueError('unconsumed memory events after executed path')
    slot_report = []
    for index, origin in enumerate(slots):
        if origin is not None:
            trig_reads_contributing.update(origin.lookups)
        slot_report.append({
            'slot_index': index,
            'written_by_sh': origin is not None,
            'has_observed_packed_q12_lineage': bool(origin and origin.lookups),
            'through_mult_hilo': bool(origin and origin.lookups and
                                      origin.via_mult and origin.via_hilo),
            'through_memory_roundtrip': bool(origin and origin.lookups and
                                             origin.via_spill),
            'has_unresolved_external_contribution': bool(origin and
                                                        origin.external_unresolved),
            'contributing_lookup_count': len(origin.lookups) if origin else 0,
        })
    return {
        'observed_packed_q12_load_count': trig_load_count,
        'distinct_q12_load_events_contributing_to_final_matrix': len(trig_reads_contributing),
        'matrix_slots_written_by_sh': sum(x['written_by_sh'] for x in slot_report),
        'matrix_slots_with_observed_q12_lineage': sum(
            x['has_observed_packed_q12_lineage'] for x in slot_report),
        'matrix_slots_with_mult_hilo_lineage': sum(
            x['through_mult_hilo'] for x in slot_report),
        'matrix_slots_with_memory_roundtrip_lineage': sum(
            x['through_memory_roundtrip'] for x in slot_report),
        'matrix_slots_with_unresolved_external_contribution': sum(
            x['has_unresolved_external_contribution'] for x in slot_report),
        'matrix_slots': slot_report,
        'pending_load_at_stop': pending is not None,
        'gameplay_angle_values_known': False,
        'bit_exact_ps1_matrix_math_proven': False,
        'private_values_emitted': False,
    }
