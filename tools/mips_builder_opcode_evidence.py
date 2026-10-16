"""Conservative static reconnaissance for the bounded Wild Arms matrix builder.

Inspects uploaded PS-X EXE machine words *without* publishing bytes, opcodes,
absolute guest addresses, immediates, matrices, or angle values. A static
word is NOT evidence that its instruction was executed during gameplay.

Candidate arithmetic shapes are restricted to straight-line regions. Every
control transfer and its delay slot force a provenance barrier. The final
output slot of the real game can only be determined by validated replay.
"""
from collections import Counter
import struct

try:
    from .audit_gp0_trig_table import TABLE_LOAD_PCS
    from .mips_matrix_operation_schedule import Node, ZERO, INPUT, UNKNOWN, _alu, classify
    from .mips_control_flow import LOADS, STORES, _gpr_destination
except ImportError:
    from audit_gp0_trig_table import TABLE_LOAD_PCS
    from mips_matrix_operation_schedule import Node, ZERO, INPUT, UNKNOWN, _alu, classify
    from mips_control_flow import LOADS, STORES, _gpr_destination


ORDERED_KINDS = (
    'mult', 'multu', 'mflo', 'mfhi', 'sra12', 'sra_other', 'addu',
    'add', 'sll2', 'andi_0fff', 'lw', 'lh', 'lhu', 'sh',
    'sw', 'sb', 'jr_ra', 'jal', 'control_other', 'nop', 'other',
)
SCHEDULES = ('single_product_sra12', 'shift_after_three_products',
             'shift_each_of_three_products')


def _opcode_kind(word):
    op = word >> 26
    rs, rt, rd, sa, fn = ((word >> 21) & 31, (word >> 16) & 31,
                           (word >> 11) & 31, (word >> 6) & 31, word & 63)
    if word == 0:
        return 'nop'
    if op == 0:
        if fn == 24 and rd == 0 and sa == 0: return 'mult'
        if fn == 25 and rd == 0 and sa == 0: return 'multu'
        if fn == 18 and rs == rt == sa == 0: return 'mflo'
        if fn == 16 and rs == rt == sa == 0: return 'mfhi'
        if fn == 3 and rs == 0: return 'sra12' if sa == 12 else 'sra_other'
        if fn == 0 and rs == 0 and sa == 2: return 'sll2'
        if fn == 33 and sa == 0: return 'addu'
        if fn == 32 and sa == 0: return 'add'
        if fn == 8 and rs == 31 and rt == rd == sa == 0: return 'jr_ra'
        if fn in (8, 9): return 'control_other'
        return 'other'
    if op == 12 and (word & 65535) == 4095: return 'andi_0fff'
    if op == 35: return 'lw'
    if op == 33: return 'lh'
    if op == 37: return 'lhu'
    if op == 41: return 'sh'
    if op == 43: return 'sw'
    if op == 40: return 'sb'
    if op == 3: return 'jal'
    if op in (1, 2, 4, 5, 6, 7, 20, 21, 22, 23): return 'control_other'
    return 'other'


def _is_control(word):
    op = word >> 26
    return (op in (1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23) or
            (op == 0 and (word & 63) in (8, 9)))


def _unmodeled_provenance(word):
    """Invalidate local GPR/HI/LO claims after an unmodeled opcode.

    In particular COP2 MFC2/CFC2 can transfer values into GPRs; ignoring it
    could falsely attach an earlier signed-product motif to a later SH.
    """
    op, fn = word >> 26, word & 63
    if op == 0:
        return fn not in (0, 2, 3, 4, 6, 7, 8, 9, 16, 17, 18, 19,
                          24, 25, 32, 33, 34, 35, 36, 37, 38, 39, 42, 43)
    return op not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                      32, 33, 35, 36, 37, 40, 41, 43, 20, 21, 22, 23)


def _fresh():
    regs = [INPUT] * 32
    regs[0] = ZERO
    return regs, UNKNOWN, UNKNOWN, None


def inspect(image, base, start, end, *, known_lookup_pcs=TABLE_LOAD_PCS,
            matrix_base_gpr=5, slot_count=9):
    """Report opcode evidence over [start, end], inclusive.

    This is *only static evidence*: words can be dead code or reached from
    external branches. Local schedule candidates are hints, not verified
    numeric formulae or proofs of actual matrix writes.
    """
    if (not all(isinstance(v, int) for v in (base, start, end, slot_count,
                                              matrix_base_gpr)) or
            base & 3 or start & 3 or end & 3 or len(image) & 3 or
            start < base or end < start or end + 4 > base + len(image) or
            (end - start) // 4 + 1 > 4096 or
            not 1 <= slot_count <= 128 or not 1 <= matrix_base_gpr <= 31):
        raise ValueError('invalid static builder image/range')
    lookup_pcs = frozenset(known_lookup_pcs)
    if any(not isinstance(pc, int) or pc & 3 for pc in lookup_pcs):
        raise ValueError('invalid known lookup sites')
    known_inside = lookup_pcs.intersection(range(start, end + 4, 4))
    counts = Counter()
    candidates = Counter()
    candidate_slots = set()
    static_sh_slots = Counter()
    other_sh = 0
    observed_known_lw = 0
    control_barriers = 0
    unsupported_provenance_barriers = 0
    delay_slot_matrix_sh_sites = 0
    # Conservative local symbolic provenance, discarded at every transfer.
    regs, hi, lo, pending = _fresh()
    skip_delay_slot = False
    for pc in range(start, end + 4, 4):
        word, = struct.unpack_from('<I', image, pc - base)
        kind = _opcode_kind(word)
        counts[kind] += 1
        if pc in lookup_pcs and kind == 'lw':
            observed_known_lw += 1
        if skip_delay_slot:
            # Branch-likely may annul it; no unconditional path evidence.
            # Still count this SH as a physical code site, separately.
            if kind == 'sh':
                rs = (word >> 21) & 31
                raw_offset = word & 65535
                offset = raw_offset - 65536 if raw_offset & 32768 else raw_offset
                if rs == matrix_base_gpr and offset in range(0,slot_count*2,2):
                    delay_slot_matrix_sh_sites += 1
            regs, hi, lo, pending = _fresh()
            skip_delay_slot = False
            continue
        if _is_control(word):
            control_barriers += 1
            regs, hi, lo, pending = _fresh()
            skip_delay_slot = True
            continue
        if _unmodeled_provenance(word):
            unsupported_provenance_barriers += 1
            regs, hi, lo, pending = _fresh()
            continue
        op = word >> 26
        rt = (word >> 16) & 31
        dst, value, next_pending = None, None, None
        if op in LOADS:
            # Effective address/data and original GPR contents are unknown.
            next_pending = (rt, Node('load')) if rt else None
        elif op in STORES:
            if op == 41:
                rs = (word >> 21) & 31
                offset = word & 0xffff
                offset = offset - 0x10000 if offset & 0x8000 else offset
                if rs == matrix_base_gpr and offset in range(0, slot_count*2, 2):
                    slot = offset // 2
                    static_sh_slots[slot] += 1
                    schedule, _ = classify(regs[rt])
                    if schedule in SCHEDULES:
                        candidates[schedule] += 1
                        candidate_slots.add(slot)
                else:
                    other_sh += 1
        else:
            # _alu is the same restricted structural recognizer used by the
            # already verified executed-op schedule. Unknown instructions are
            # forced to unknown destinations instead of preserving stale nodes.
            dst, value, hi, lo = _alu(word, regs, hi, lo)
            if dst is None:
                unknown_dest = _gpr_destination(word)
                if unknown_dest:
                    dst, value = unknown_dest, UNKNOWN
            # Incomplete HI/LO semantics must never turn unknown paths into
            # affirmative products; a fresh block uses UNKNOWN HI and LO.
        if pending is not None and pending[0] != dst and (
                next_pending is None or pending[0] != next_pending[0]):
            regs[pending[0]] = pending[1]
        if dst:
            regs[dst] = value
        regs[0] = ZERO
        pending = next_pending
    return_word, = struct.unpack_from('<I', image, end - base)
    slot_available = end + 8 <= base + len(image)
    return_slot_kind = None
    return_slot_matrix_index = None
    if slot_available:
        return_slot_word, = struct.unpack_from('<I', image, end + 4 - base)
        return_slot_kind = _opcode_kind(return_slot_word)
        if return_slot_kind == 'sh':
            rs = (return_slot_word >> 21) & 31
            offset = return_slot_word & 65535
            offset = offset - 65536 if offset & 32768 else offset
            if rs == matrix_base_gpr and offset in range(0, slot_count*2, 2):
                return_slot_matrix_index = offset // 2
    all_referenced = set(static_sh_slots)
    if return_slot_matrix_index is not None:
        all_referenced.add(return_slot_matrix_index)
    return {
        'instruction_count': (end - start)//4 + 1,
        'opcode_counts': {kind: counts[kind] for kind in ORDERED_KINDS},
        'static_matrix_sh_sites': sum(static_sh_slots.values()),
        'static_matrix_sh_slot_indices': sorted(static_sh_slots),
        'static_matrix_sh_duplicate_sites': sum(n-1 for n in static_sh_slots.values()),
        'other_sh_sites': other_sh,
        'straight_line_schedule_candidates': {name: candidates[name] for name in SCHEDULES},
        'straight_line_candidate_slot_indices': sorted(candidate_slots),
        'control_flow_barriers': control_barriers,
        'unsupported_provenance_barriers': unsupported_provenance_barriers,
        'delay_slot_matrix_sh_sites': delay_slot_matrix_sh_sites,
        'known_lookup_sites_in_range': len(known_inside),
        'known_lookup_sites_with_lw_opcode': observed_known_lw,
        'return_site_encodes_jr_ra': _opcode_kind(return_word) == 'jr_ra',
        'return_delay_slot_word_available': slot_available,
        'return_delay_slot_opcode_kind': return_slot_kind,
        'return_delay_slot_matrix_sh_slot_index': return_slot_matrix_index,
        'all_nine_slots_statically_referenced': (slot_count == 9 and
                                                 len(static_sh_slots) == 9),
        'all_nine_slots_referenced_including_return_delay_slot': (
            slot_count == 9 and len(all_referenced) == 9),
        'static_words_are_executed': False,
        'original_builder_schedule_identified': False,
        'original_gameplay_coefficients_checked': False,
        'private_values_emitted': False,
    }
