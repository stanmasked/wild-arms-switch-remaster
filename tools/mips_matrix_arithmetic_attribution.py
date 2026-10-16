"""Conservative dynamic dependencies from mismatched MIPS arithmetic to final SH.

A reported slot is a *potential downstream dependency*, not a proven numeric
cause. Requires an independently supplied arithmetic reference with identical
executed instruction sites. Never returns PCs, values, guest addresses or code.
"""
import struct

try:
    from .mips_control_flow import LOADS, STORES
    from .mips_arithmetic_event_sequence import trace_events, instruction_kind
    from .mips_store_event_sequence import trace_events as store_trace_events
except ImportError:
    from mips_control_flow import LOADS, STORES
    from mips_arithmetic_event_sequence import trace_events, instruction_kind
    from mips_store_event_sequence import trace_events as store_trace_events

MAX_LINEAGE_TOKENS = 512
MAX_REPORTED_INDICES = 32


def analyze(image, base, trace, matrix_address, expected, *, matrix_slots=9,
            guest_stopped_at_expected_pc):
    """Map wrong primary/HI event indices to last SH slot dependencies.

    Successful store events and executed arithmetic PCs are cross-checked
    before allowing attribution. Alignment errors disable attribution rather
    than guessing how a divergent reference event maps to the guest path.
    """
    if (not isinstance(image, (bytes, bytearray)) or len(image) & 3 or
            type(base) is not int or type(matrix_address) is not int or
            base & 3 or matrix_address & 1 or type(matrix_slots) is not int or
            not 1 <= matrix_slots <= 128 or
            type(guest_stopped_at_expected_pc) is not bool):
        raise ValueError('invalid arithmetic attribution configuration')
    actual = trace_events(trace)
    store_events = store_trace_events(trace)
    if not isinstance(expected, tuple) or any(not isinstance(r, tuple) or
                                               len(r) != 4 for r in expected):
        raise ValueError('unvalidated reference arithmetic events')

    output = {
        'attribution_performed': False,
        'reason_code': 'incomplete_guest_execution',
        'reference_event_alignment_confirmed': False,
        'candidate_affected_slot_indices': [],
        'mismatching_events_without_final_matrix_dependency': [],
        'matrix_slots': [{'slot_index': i, 'final_sh_observed': False,
                          'candidate_mismatch_event_indices': [],
                          'candidate_primary_mismatch_indices': [],
                          'candidate_hi_mismatch_indices': []}
                         for i in range(matrix_slots)],
        'mismatch_index_lists_truncated': False,
        'synthetic_dynamic_dependency_only': True,
        'proven_numeric_causation': False,
        'original_gameplay_equivalence_proven': False,
        'private_values_emitted': False,
    }
    if not guest_stopped_at_expected_pc:
        return output
    if (len(expected) != len(actual) or
            any(ref[:2] != act[:2] for ref, act in zip(expected, actual))):
        output['reason_code'] = 'arithmetic_event_alignment_failed'
        return output
    output['reference_event_alignment_confirmed'] = True
    bad_tokens = set()
    for i, (ref, act) in enumerate(zip(expected, actual)):
        if ref[2] != act[2]:
            bad_tokens.add(i*2)
        if ref[3] != act[3]:
            bad_tokens.add(i*2 + 1)
    mismatch_indices = {token // 2 for token in bad_tokens}

    # Immutable token sets; primary token 2*i, multiplication HI token 2*i+1.
    empty = frozenset()
    regs = [empty for _ in range(32)]
    hi = lo = empty
    pending = None
    ram_shadow = {}                 # address -> token set (byte-granular)
    slots = [None] * matrix_slots   # last *successful exact* SH only
    event_cursor = 0
    load_cursor = 0
    store_cursor = 0
    budget_exceeded = False

    def union(*origins):
        nonlocal budget_exceeded
        combined = frozenset().union(*origins)
        if len(combined) > MAX_LINEAGE_TOKENS:
            budget_exceeded = True
            return empty
        return combined

    for pc in trace['visited_pcs']:
        if (type(pc) is not int or pc < base or (pc-base) & 3 or
                pc + 4 > base + len(image)):
            raise ValueError('invalid executed PC in matrix attribution')
        word, = struct.unpack_from('<I', image, pc-base)
        op, rs, rt, rd, sa, fn = (word >> 26, (word >> 21) & 31,
                                (word >> 16) & 31, (word >> 11) & 31,
                                (word >> 6) & 31, word & 63)
        kind = instruction_kind(word)
        token = empty
        if kind:
            if event_cursor >= len(actual) or actual[event_cursor][:2] != (pc, kind):
                raise ValueError('missing or misaligned executed arithmetic event')
            token = frozenset((2*event_cursor,))
            event_cursor += 1
        dest = None
        next_pending = None
        value = empty
        if op in LOADS:
            if load_cursor >= len(trace['load_accesses']):
                raise ValueError('missing executed load')
            event = trace['load_accesses'][load_cursor]
            load_cursor += 1
            if (len(event) != 4 or event[0] != pc or
                    event[2] != LOADS[op] or event[3] != rt):
                raise ValueError('inconsistent executed load')
            address, width = event[1], event[2]
            if (type(address) is not int or address < 0 or
                    address % width):
                raise ValueError('invalid executed load address')
            data = union(*(ram_shadow.get(address+j, empty) for j in range(width)))
            next_pending = (rt, data) if rt else None
        elif op in STORES:
            if store_cursor >= len(store_events):
                raise ValueError('missing executed store')
            store_pc, addr, width = store_events[store_cursor]
            store_cursor += 1
            if store_pc != pc or width != STORES[op]:
                raise ValueError('inconsistent executed store instruction')
            stored = regs[rt]    # before pending load retirement
            for j in range(width):
                ram_shadow[addr+j] = stored
            for index in range(matrix_slots):
                start = matrix_address + 2*index
                if addr < start+2 and addr+width > start:
                    slots[index] = stored if op == 41 and addr == start else None
        elif op == 0:
            if word == 0 or fn == 8:
                pass
            elif fn == 9:          # JALR writes PC-derived link, not arithmetic
                dest = rd
            elif fn in (24, 25):
                sources = union(regs[rs], regs[rt])
                lo = union(sources, token)
                hi = union(sources, frozenset((2*(event_cursor-1)+1,)))
            elif fn in (16, 18):
                dest = rd
                value = union(hi if fn == 16 else lo, token)
            elif fn == 17:
                hi = regs[rs]
            elif fn == 19:
                lo = regs[rs]
            elif fn in (0, 2, 3):
                dest = rd
                value = union(regs[rt], token)
            elif fn in (4, 6, 7):
                dest = rd
                value = union(regs[rs], regs[rt], token)
            elif fn in (32, 33, 34, 35, 36, 37, 38, 39, 42, 43):
                dest = rd
                value = union(regs[rs], regs[rt], token)
            else:
                raise ValueError('unsupported executed MIPS SPECIAL dependency')
        elif op in (8, 9, 10, 11, 12, 13, 14):
            dest, value = rt, regs[rs]
        elif op == 15:
            dest = rt
        elif op == 3:  # JAL writes a link PC, not data
            dest = 31
        elif op in (1, 2, 4, 5, 6, 7, 20, 21, 22, 23):
            pass
        else:
            raise ValueError('unsupported executed opcode in dependency replay')
        # Same one-instruction pending load retirement as the concrete runner.
        if pending is not None and (pending[0] != dest or op in LOADS):
            regs[pending[0]] = pending[1]
        if dest:
            regs[dest] = value
        regs[0] = empty
        pending = next_pending

    if (event_cursor != len(actual) or store_cursor != len(store_events) or
            load_cursor != len(trace['load_accesses'])):
        raise ValueError('unconsumed guest replay events')
    if budget_exceeded:
        output['reason_code'] = 'dependency_budget_exceeded'
        return output

    affected = set()
    linked = set()
    truncated = False
    for index, deps in enumerate(slots):
        primary = sorted({token//2 for token in (deps or empty) & bad_tokens
                          if token % 2 == 0})
        secondary = sorted({token//2 for token in (deps or empty) & bad_tokens
                            if token % 2 == 1})
        combined = sorted(set(primary) | set(secondary))
        if combined:
            affected.add(index)
            linked.update(combined)
        if any(len(items) > MAX_REPORTED_INDICES for items in (primary, secondary, combined)):
            truncated = True
        output['matrix_slots'][index].update({
            'final_sh_observed': deps is not None,
            'candidate_mismatch_event_indices': combined[:MAX_REPORTED_INDICES],
            'candidate_primary_mismatch_indices': primary[:MAX_REPORTED_INDICES],
            'candidate_hi_mismatch_indices': secondary[:MAX_REPORTED_INDICES],
        })
    orphan = sorted(mismatch_indices - linked)
    if len(orphan) > MAX_REPORTED_INDICES:
        truncated = True
    output.update({
        'attribution_performed': True,
        'reason_code': 'aligned_dynamic_dependencies',
        'candidate_affected_slot_indices': sorted(affected),
        'mismatching_events_without_final_matrix_dependency': orphan[:MAX_REPORTED_INDICES],
        'mismatch_index_lists_truncated': truncated,
    })
    return output
