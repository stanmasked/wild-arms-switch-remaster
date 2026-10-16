"""Conservative shadow provenance of successful packed Q12 MIPS table lookups.

Consumes an already-executed MIPS PC sequence and successful load events.
Never emits guest PC/address, table index, register value or sine/cosine word.
A dependency of the table address is NOT proof of a gameplay angle source.
"""
from dataclasses import dataclass
import struct

try:
    from .audit_gp0_trig_table import TABLE, ENTRIES
    from .mips_fixed32 import sign_extend16
    from .mips_control_flow import LOADS, STORES
except ImportError:
    from audit_gp0_trig_table import TABLE, ENTRIES
    from mips_fixed32 import sign_extend16
    from mips_control_flow import LOADS, STORES


@dataclass(frozen=True)
class Origin:
    roots: frozenset = frozenset()
    memory_derived: bool = False
    shifted_by_two: bool = False
    masked_12bit: bool = False
    unknown: bool = False


def combine(*items):
    return Origin(
        frozenset().union(*(item.roots for item in items)),
        any(item.memory_derived for item in items),
        any(item.shifted_by_two for item in items),
        any(item.masked_12bit for item in items),
        any(item.unknown for item in items),
    )


def _advance(word, regs, hi, lo):
    """Compute shadow GPR/HI/LO writes; return (destination, origin, hi, lo).

    Delayed loads are handled by the caller, never by this ALU helper.
    A rejected encoding must not be used as evidence for an index origin.
    """
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    sa, fn = (word >> 6) & 31, word & 63
    a, b = regs[rs], regs[rt]
    if word == 0:
        return None, None, hi, lo
    if op == 0:
        if fn in (8, 9):
            # JR/JALR: GPR is read for the target, but only JALR links.
            if rt or sa or (fn == 8 and rd):
                raise ValueError('malformed indirect jump')
            return (rd if fn == 9 else None), Origin(), hi, lo
        if fn in (0, 2, 3) and rs == 0:
            return rd, Origin(b.roots, b.memory_derived,
                              b.shifted_by_two or (fn == 0 and sa == 2),
                              b.masked_12bit, b.unknown), hi, lo
        if fn in (4, 6, 7) and sa == 0:
            return rd, combine(a, b), hi, lo
        if fn in (24, 25) and rd == 0 and sa == 0:
            return None, None, combine(a, b), combine(a, b)
        if fn in (16, 18) and rs == 0 and rt == 0 and sa == 0:
            value = hi if fn == 16 else lo
            return rd, value if value is not None else Origin(unknown=True), hi, lo
        if fn in (17, 19) and rt == 0 and rd == 0 and sa == 0:
            return (None, None, a if fn == 17 else hi,
                    a if fn == 19 else lo)
        if fn in (32, 33, 34, 35, 36, 37, 38, 39, 42, 43) and sa == 0:
            return rd, combine(a, b), hi, lo
        raise ValueError('unsupported SPECIAL provenance')
    if op in (8, 9, 10, 11, 12, 13, 14):
        mask = a.masked_12bit or (op == 12 and (word & 0xffff) == 0x0fff)
        return rt, Origin(a.roots, a.memory_derived, a.shifted_by_two,
                          mask, a.unknown), hi, lo
    if op == 15 and rs == 0:
        return rt, Origin(), hi, lo  # LUI provides literal base.
    if op == 3:
        return 31, Origin(), hi, lo
    if op in (1, 2, 4, 5, 6, 7, 20, 21, 22, 23):
        return None, None, hi, lo
    if op in STORES:
        return None, None, hi, lo
    raise ValueError('unsupported provenance instruction')


def summarize(image, base, visited_pcs, successful_loads, *,
              table_address=TABLE, table_entries=ENTRIES):
    """Summarize dependencies of *confirmed* packed Q12 LW addresses.

    Uses load events recorded by concrete replay to confirm address ranges;
    static instruction matching alone is never considered a table read.
    """
    if (base & 3 or len(image) & 3 or table_address & 3 or table_entries < 1):
        raise ValueError('invalid MIPS image or table boundaries')
    regs = [Origin(roots=frozenset({r})) for r in range(32)]
    regs[0] = Origin()
    hi = lo = None
    pending = None
    loads = iter(successful_loads)
    count = 0
    roots = set()
    per_root = {}
    shifted = masked = memory = unknown = constant = 0
    for pc in visited_pcs:
        if not isinstance(pc, int) or pc < base or (pc-base) % 4 or pc + 4 > base + len(image):
            raise ValueError('visited instruction outside image')
        word, = struct.unpack_from('<I', image, pc-base)
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        immediate_write = None
        new_value = None
        next_pending = None
        if op in LOADS:
            event = next(loads, None)
            if (event is None or len(event) != 4 or event[0] != pc
                    or event[2] != LOADS[op] or event[3] != rt):
                raise ValueError('load event does not match executed instruction')
            addr = event[1]
            if not isinstance(addr, int) or addr < 0 or addr % LOADS[op]:
                raise ValueError('invalid load address')
            # Effective address = base GPR + sign-extended immediate.
            address_origin = regs[rs]
            if (op == 35 and table_address <= addr
                    and addr + 4 <= table_address + table_entries * 4
                    and (addr - table_address) % 4 == 0):
                count += 1
                roots.update(address_origin.roots)
                for root in address_origin.roots:
                    per_root[root] = per_root.get(root, 0) + 1
                shifted += address_origin.shifted_by_two
                masked += address_origin.masked_12bit
                memory += address_origin.memory_derived
                unknown += address_origin.unknown
                constant += not (address_origin.roots or
                                 address_origin.memory_derived or
                                 address_origin.unknown)
            # Memory-provided DATA depend on a prior load regardless of whether
            # its address came from a literal or an input register.
            next_pending = (rt, Origin(address_origin.roots, True,
                                        False, False, address_origin.unknown)) if rt else None
        else:
            immediate_write, new_value, hi, lo = _advance(word, regs, hi, lo)
        if pending is not None:
            dest, origin = pending
            if dest != immediate_write and (next_pending is None or dest != next_pending[0]):
                regs[dest] = origin
        if immediate_write:
            regs[immediate_write] = new_value
        regs[0] = Origin()
        pending = next_pending
    if next(loads, None) is not None:
        raise ValueError('unconsumed successful load events')
    return {
        'packed_table_loads_with_provenance': count,
        'address_dependency_gprs': sorted(roots),
        'address_dependency_lookup_counts': [
            {'gpr': root, 'lookup_count': per_root[root]} for root in sorted(per_root)],
        'lookups_with_shift_left_two_in_address_chain': shifted,
        'lookups_with_12bit_mask_in_address_chain': masked,
        'lookups_with_prior_memory_read_in_address_chain': memory,
        'lookups_with_unknown_address_provenance': unknown,
        'lookups_with_no_external_address_dependencies': constant,
        'original_angle_values_recovered': False,
        'input_gpr_proven_to_be_game_angle': False,
        'private_values_emitted': False,
    }
