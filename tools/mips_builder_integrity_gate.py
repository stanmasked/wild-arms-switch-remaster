"""Aggregate independently checked PS1 MIPS caller->Q12->matrix->return evidence.

This is an *audit of a synthetic guest replay*, NOT proof that these inputs,
branch choices, or matrix coefficients occur in original Wild Arms gameplay.
No original values, addresses, opcode words or per-register contents are emitted.
"""

REQUIREMENTS = (
    'caller_jal_and_a1_frame',
    'executed_caller_to_builder_transfer',
    'executed_builder_to_caller_return',
    'bounded_guest_completed',
    'all_known_lookup_sites_present',
    'all_known_lookup_sites_executed_with_packed_lw',
    'address_provenance_for_all_lookups',
    'all_nine_final_sh_match_builder_sites',
    'all_nine_coefficients_retain_q12_lineage',
    'all_shadow_matrix_reports_agree',
)


def evaluate(*, static, caller_linkage, execution, builder_execution,
             operation_schedule, value_lineage, trig_address_provenance,
             expected_lookup_sites=6, expected_matrix_slots=9):
    """Perform a strict logical conjunction; do not infer data from missing keys.

    The transfer predicates must have been computed from completed MIPS delay
    slots. Matrix predicates refer to the *final* successful SH for each slot;
    overlapping SB/SW invalidates the older evidence.
    """
    if (not isinstance(expected_lookup_sites, int) or expected_lookup_sites < 1
            or not isinstance(expected_matrix_slots, int)
            or not 1 <= expected_matrix_slots <= 128):
        raise ValueError('invalid builder-integrity expectations')
    if any(not isinstance(x, dict) for x in (
            static, caller_linkage, execution, builder_execution,
            operation_schedule, value_lineage, trig_address_provenance)):
        raise ValueError('missing or malformed integrity evidence')

    slots = builder_execution.get('matrix_slots', ())
    op_slots = operation_schedule.get('matrix_slots', ())
    value_slots = value_lineage.get('matrix_slots', ())
    slot_shape_ok = (all(isinstance(items, (tuple, list)) and
                         len(items) == expected_matrix_slots
                         for items in (slots, op_slots, value_slots)) and
                     all(all(isinstance(item, dict) and
                                 item.get('slot_index') == idx
                                 for idx, item in enumerate(items))
                         for items in (slots, op_slots, value_slots)))
    slot_agreement = bool(slot_shape_ok and all(
        (item.get('final_successful_sh_observed') is
         (op.get('schedule') != 'not_written')) and
        (item.get('final_successful_sh_observed') ==
         value.get('written_by_sh')) and
        (item.get('has_observed_packed_q12_lineage') ==
         value.get('has_observed_packed_q12_lineage'))
        for item, op, value in zip(slots, op_slots, value_slots)))

    checks = {
        'caller_jal_and_a1_frame': (
            caller_linkage.get('linkage_confirmed') is True and
            execution.get('frame_layout') == 'a1_sp_plus_16' and
            execution.get('caller_jal_executed') is True),
        'executed_caller_to_builder_transfer': (
            execution.get('builder_entry_reached') is True and
            execution.get('caller_transfer_completed') is True),
        'executed_builder_to_caller_return': (
            execution.get('returned_to_caller') is True and
            builder_execution.get('jr_ra_return_transfer_completed') is True),
        'bounded_guest_completed': (
            execution.get('reason') == 'stop_pc' and
            operation_schedule.get('guest_execution_completed') is True and
            builder_execution.get('guest_execution_completed') is True),
        'all_known_lookup_sites_present': (
            static.get('known_lookup_sites_in_range') == expected_lookup_sites and
            static.get('known_lookup_sites_with_lw_opcode') == expected_lookup_sites),
        'all_known_lookup_sites_executed_with_packed_lw': (
            builder_execution.get('known_trig_lw_sites_executed') == expected_lookup_sites and
            builder_execution.get('known_trig_lw_sites_with_verified_packed_reads') == expected_lookup_sites),
        'address_provenance_for_all_lookups': (
            trig_address_provenance.get('packed_table_loads_with_provenance') ==
            builder_execution.get('successful_packed_table_load_events_in_trace') and
            trig_address_provenance.get('packed_table_loads_with_provenance', 0) >=
            expected_lookup_sites and
            trig_address_provenance.get('lookups_with_unknown_address_provenance') == 0),
        'all_nine_final_sh_match_builder_sites': (
            slot_shape_ok and
            builder_execution.get('final_matrix_slots_written_by_sh') == expected_matrix_slots and
            builder_execution.get('final_matrix_slots_verified_against_static_sh_site') == expected_matrix_slots and
            all(item.get('final_sh_matches_static_a1_offset') is True for item in slots)),
        'all_nine_coefficients_retain_q12_lineage': (
            slot_shape_ok and
            value_lineage.get('matrix_slots_with_observed_q12_lineage') == expected_matrix_slots and
            all(item.get('has_observed_packed_q12_lineage') is True for item in slots)),
        'all_shadow_matrix_reports_agree': slot_agreement,
    }
    failed = [name for name in REQUIREMENTS if not checks[name]]
    return {
        'synthetic_end_to_end_evidence_complete': not failed,
        'requirements_satisfied': len(REQUIREMENTS) - len(failed),
        'requirements_total': len(REQUIREMENTS),
        'checks': {name: checks[name] for name in REQUIREMENTS},
        'unmet_requirement_codes': failed,
        'expected_known_lookup_sites': expected_lookup_sites,
        'expected_final_matrix_slots': expected_matrix_slots,
        'original_gameplay_inputs_verified': False,
        'original_playstation_matrix_values_compared': False,
        'playable_native_switch_build_proven': False,
        'private_values_emitted': False,
    }
