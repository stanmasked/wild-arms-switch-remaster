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
_PS1_RAM_WINDOW = 0x800000
_PS1_RAM_SIZE = 0x200000


def _ps1_ram_offset(address):
    """Conservative PS1 2 MiB RAM offset, including its 8 MiB mirrors.

    This is a *guard*, not guest memory translation. Do not use it to
    synthesize concrete values or claim MIPS physical memory fidelity.
    """
    if type(address) is not int:
        return None
    if (0 <= address < _PS1_RAM_WINDOW or
            0x80000000 <= address < 0x80000000 + _PS1_RAM_WINDOW or
            0xa0000000 <= address < 0xa0000000 + _PS1_RAM_WINDOW):
        return address & (_PS1_RAM_SIZE - 1)
    return None


def _may_write_replayed_code(address, width, base, image_length):
    """Detect direct and RAM-mirrored writes into static guest code."""
    if address < base + image_length and address + width > base:
        return True
    code_start = _ps1_ram_offset(base)
    code_end = _ps1_ram_offset(base + image_length - 1)
    if code_start is None or code_end is None:
        return False
    # A linear loaded image may itself cross the 2 MiB RAM mirror.
    for byte in range(address, address + width):
        physical = _ps1_ram_offset(byte)
        if (physical is not None and
                ((physical - code_start) % _PS1_RAM_SIZE) < image_length):
            return True
    return False


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
        'mismatch_dependent_address_observed': False,
        'mismatch_dependent_control_observed': False,
        'executed_code_write_observed': False,
        'ram_alias_access_observed': False,
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
    mismatch_dependent_address = False
    mismatch_dependent_control = False
    executed_code_write = False
    ram_alias_access = False
    # The concrete MappedMemory model uses disjoint virtual regions, not PS1
    # physical RAM. Do not turn observed virtual writes into fabricated alias
    # values: withhold lineage whenever separate virtual bytes alias RAM.
    physical_virtual_accesses = {}
    matrix_physical_bytes = {
        physical for offset in range(matrix_slots * 2)
        if (physical := _ps1_ram_offset(matrix_address + offset)) is not None
    }

    def observe_ram_access(address, width, *, store=False):
        nonlocal ram_alias_access
        for offset in range(width):
            virtual = address + offset
            physical = _ps1_ram_offset(virtual)
            if physical is None:
                continue
            previous = physical_virtual_accesses.get(physical)
            if previous is not None and previous != virtual:
                ram_alias_access = True
            else:
                physical_virtual_accesses[physical] = virtual
            # An SH to a virtual mirror of the output buffer is invisible
            # to the current exact-virtual final-slot tracker.
            if (store and physical in matrix_physical_bytes and
                    not matrix_address <= virtual < matrix_address + matrix_slots*2):
                ram_alias_access = True

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
        # A mismatched arithmetic result can change *where* memory is read or
        # written, even if it never reaches the value being stored. Following
        # observed addresses alone would then understate possible effects.
        if op in LOADS or op in STORES:
            if regs[rs] & bad_tokens:
                mismatch_dependent_address = True
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
            observe_ram_access(address, width)
            data = union(*(ram_shadow.get(address+j, empty) for j in range(width)))
            next_pending = (rt, data) if rt else None
        elif op in STORES:
            if store_cursor >= len(store_events):
                raise ValueError('missing executed store')
            store_pc, addr, width = store_events[store_cursor]
            store_cursor += 1
            if store_pc != pc or width != STORES[op]:
                raise ValueError('inconsistent executed store instruction')
            observe_ram_access(addr, width, store=True)
            # A CPU write into the replayed executable invalidates later
            # static-image instruction decoding: execute() intentionally does
            # not fetch modified code. Even a same-value write is conservatively
            # treated as unverified (we do not compare private code bytes).
            if _may_write_replayed_code(addr, width, base, len(image)):
                executed_code_write = True
            stored = regs[rt]    # before pending load retirement
            for j in range(width):
                ram_shadow[addr+j] = stored
            for index in range(matrix_slots):
                start = matrix_address + 2*index
                if addr < start+2 and addr+width > start:
                    slots[index] = stored if op == 41 and addr == start else None
        elif op == 0:
            if word == 0 or fn == 8:
                if fn == 8 and regs[rs] & bad_tokens:  # JR target
                    mismatch_dependent_control = True
            elif fn == 9:          # JALR writes PC-derived link, not arithmetic
                if regs[rs] & bad_tokens:
                    mismatch_dependent_control = True
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
            # Direct J/JAL targets are constant. Conditional control tests
            # their current operands *before* delayed loads retire.
            if op in (1, 6, 7, 22, 23):
                control_deps = regs[rs]
            elif op in (4, 5, 20, 21):
                control_deps = union(regs[rs], regs[rt])
            else:
                control_deps = empty
            if control_deps & bad_tokens:
                mismatch_dependent_control = True
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
    if executed_code_write:
        output['reason_code'] = 'guest_code_write_unmodeled'
        output['executed_code_write_observed'] = True
        return output
    if ram_alias_access:
        # No physical alias coherence in the concrete runner or byte lineage.
        # Affected/unlinked slot candidates could otherwise be misleading.
        output['reason_code'] = 'ram_alias_access_unmodeled'
        output['ram_alias_access_observed'] = True
        return output
    if mismatch_dependent_address or mismatch_dependent_control:
        # An observed execution path is insufficient to rule out stores made
        # through another pointer or another branch path on real hardware.
        # Withhold *all* per-slot candidates, including orphan conclusions.
        output['reason_code'] = 'mismatch_dependent_execution_path'
        output['mismatch_dependent_address_observed'] = mismatch_dependent_address
        output['mismatch_dependent_control_observed'] = mismatch_dependent_control
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
