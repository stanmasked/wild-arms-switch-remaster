"""Correlate static Wild Arms matrix builder sites with concrete guest replay.

This is a narrowly scoped *synthetic* execution attestation.  Instruction
presence is not execution; visiting an SH word is not evidence that it wrote
to the matrix unless a successful concrete store hit its intended address.
No private guest PCs, addresses, instructions, registers or values are output.
"""
import struct

try:
    from .audit_gp0_trig_table import TABLE, ENTRIES, TABLE_LOAD_PCS
    from .mips_control_flow import LOADS, STORES
except ImportError:
    from audit_gp0_trig_table import TABLE, ENTRIES, TABLE_LOAD_PCS
    from mips_control_flow import LOADS, STORES


RECOGNIZED = frozenset(('single_product_sra12',
                        'shift_after_three_products',
                        'shift_each_of_three_products'))


def _slot_syntax(word, slots):
    """Index of SH slot relative to a1, or None (including non-SH)."""
    if word >> 26 != 41 or (word >> 21) & 31 != 5:
        return None
    offset = word & 65535
    if offset & 32768:
        offset -= 65536
    return offset // 2 if offset in range(0, slots * 2, 2) else None


def summarize(image, base, start, end, trace, matrix_address, *,
              operation_schedule, value_lineage, table_address=TABLE,
              table_entries=ENTRIES, known_lookup_pcs=TABLE_LOAD_PCS,
              matrix_slots=9):
    """Cross-check static instruction sites with actually completed load/SH events.

    The trace comes from the bounded interpreter; the operation and value
    reports come from independent, previously tested shadow interpreters.
    Never asserts that supplied initial GPRs equal real game state.
    """
    ints = (base, start, end, matrix_address, table_address,
            table_entries, matrix_slots)
    if (not all(isinstance(v, int) for v in ints) or
            base & 3 or start & 3 or end & 3 or matrix_address & 1 or
            table_address & 3 or start < base or end < start or
            end + 4 > base + len(image) or len(image) & 3 or
            not 1 <= matrix_slots <= 128 or table_entries < 1):
        raise ValueError('invalid execution evidence range')
    if (len(operation_schedule['matrix_slots']) != matrix_slots or
            len(value_lineage['matrix_slots']) != matrix_slots or
            any(x['slot_index'] != i for i, x in
                enumerate(operation_schedule['matrix_slots'])) or
            any(x['slot_index'] != i for i, x in
                enumerate(value_lineage['matrix_slots']))):
        raise ValueError('shadow matrix-slot reports are inconsistent')
    known = frozenset(known_lookup_pcs)
    if any(not isinstance(pc, int) or pc & 3 for pc in known):
        raise ValueError('invalid known Q12 code sites')

    def word_at(pc):
        if (not isinstance(pc, int) or pc < base or (pc-base) % 4 or
                pc + 4 > base + len(image)):
            raise ValueError('executed PC outside supplied code image')
        return struct.unpack_from('<I', image, pc-base)[0]

    static_sh = set()
    for pc in range(start, end + 4, 4):
        if _slot_syntax(word_at(pc), matrix_slots) is not None:
            static_sh.add(pc)
    # The JR $ra delay slot can contain the last matrix coefficient store.
    return_word = word_at(end)
    is_jr_ra = (return_word == ((31 << 21) | 8))
    if (is_jr_ra and end+8 <= base+len(image) and
            _slot_syntax(word_at(end+4), matrix_slots) is not None):
        static_sh.add(end+4)

    visited = tuple(trace['visited_pcs'])
    visited_set = set(visited)
    concrete_loads = iter(trace['load_accesses'])
    concrete_stores = iter(trace['store_addresses'])
    final_slots = [None] * matrix_slots
    observed_matrix_sh_sites = set()
    known_lookup_sites_executed = set()
    verified_lookup_sites = set()
    successful_table_loads = 0
    returned_jr = any(source == end and kind == 'jr_ra'
                      for source, kind, target in trace['control_transfers'])
    for pc in visited:
        word = word_at(pc)
        op = word >> 26
        rt = (word >> 16) & 31
        in_builder = start <= pc <= end
        if in_builder and op == 35 and pc in known:
            known_lookup_sites_executed.add(pc)
        if op in LOADS:
            event = next(concrete_loads, None)
            if (event is None or len(event) != 4 or
                    event[0] != pc or event[2] != LOADS[op] or
                    event[3] != rt):
                raise ValueError('executed load event mismatch')
            address, width = event[1], event[2]
            if not isinstance(address, int) or address < 0 or address % width:
                raise ValueError('invalid successful load event address')
            if (op == 35 and table_address <= address and
                    address + 4 <= table_address + table_entries * 4 and
                    (address-table_address) % 4 == 0):
                successful_table_loads += 1
                if in_builder and pc in known:
                    verified_lookup_sites.add(pc)
        elif op in STORES:
            address = next(concrete_stores, None)
            width = STORES[op]
            if not isinstance(address, int) or address < 0 or address % width:
                raise ValueError('executed store event mismatch')
            # Last write wins: SB/SW and wrong-base SH can revoke an earlier
            # syntactically verified matrix SH for a given output halfword.
            for index in range(matrix_slots):
                slot_address = matrix_address + 2 * index
                if address < slot_address + 2 and address + width > slot_address:
                    matched = (op == 41 and address == slot_address and
                               pc in static_sh and
                               _slot_syntax(word, matrix_slots) == index and
                               (pc <= end or returned_jr))
                    final_slots[index] = (pc, matched) if op == 41 and address == slot_address else None
                    if matched:
                        observed_matrix_sh_sites.add(pc)
    if next(concrete_loads, None) is not None or next(concrete_stores, None) is not None:
        raise ValueError('unconsumed guest memory-access events')

    executed_builder = {pc for pc in visited_set if start <= pc <= end}
    confirmed = 0
    dynamic_slots = 0
    recognized = 0
    output = []
    for i, record in enumerate(final_slots):
        schedule = operation_schedule['matrix_slots'][i]
        value = value_lineage['matrix_slots'][i]
        is_written = record is not None
        matched = bool(record and record[1])
        # The separate operation/value interpreters should agree on which
        # slots retained a final SH; a disagreement is not safe to report.
        if (schedule['schedule'] == 'not_written') != (not is_written):
            raise ValueError('instruction schedule and store trace disagree')
        if bool(value['written_by_sh']) != is_written:
            raise ValueError('Q12 lineage and store trace disagree')
        dynamic_slots += is_written
        confirmed += matched
        recognized += bool(matched and schedule['schedule'] in RECOGNIZED)
        output.append({
            'slot_index': i,
            'final_successful_sh_observed': is_written,
            'final_sh_matches_static_a1_offset': matched,
            'final_sh_from_verified_return_delay_slot': bool(
                matched and record[0] == end+4 and returned_jr),
            'observed_arithmetic_schedule': schedule['schedule'],
            'has_observed_packed_q12_lineage': bool(value['has_observed_packed_q12_lineage']),
        })
    return {
        'static_builder_instruction_count': (end-start)//4 + 1,
        'distinct_builder_instructions_executed': len(executed_builder),
        'static_matrix_sh_syntax_site_count': len(static_sh),
        'static_matrix_sh_syntax_sites_executed': len(static_sh & visited_set),
        'static_matrix_sh_syntax_sites_not_executed': len(static_sh - visited_set),
        'successful_sh_sites_matching_static_matrix_syntax': len(observed_matrix_sh_sites),
        'final_matrix_slots_written_by_sh': dynamic_slots,
        'final_matrix_slots_verified_against_static_sh_site': confirmed,
        'final_verified_slots_with_recognized_arithmetic_schedule': recognized,
        'known_trig_lw_sites_executed': len(known_lookup_sites_executed),
        'known_trig_lw_sites_with_verified_packed_reads': len(verified_lookup_sites),
        'successful_packed_table_load_events_in_trace': successful_table_loads,
        'jr_ra_return_transfer_completed': returned_jr,
        'guest_execution_completed': bool(trace['completed']),
        'matrix_slots': output,
        'runtime_inputs_are_synthetic': True,
        'original_builder_reachability_proven': False,
        'original_gameplay_coefficients_checked': False,
        'private_values_emitted': False,
    }
