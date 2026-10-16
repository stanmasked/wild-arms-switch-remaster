"""Proof-gate tests use aggregate counters only, never original game assets."""
import copy
import unittest
from tools.mips_builder_integrity_gate import evaluate, REQUIREMENTS


def evidence():
    slots = [{'slot_index':i, 'final_successful_sh_observed':True,
              'final_sh_matches_static_a1_offset':True,
              'has_observed_packed_q12_lineage':True} for i in range(9)]
    ops = [{'slot_index':i,'schedule':'single_product_sra12'} for i in range(9)]
    vals = [{'slot_index':i,'written_by_sh':True,
             'has_observed_packed_q12_lineage':True} for i in range(9)]
    return {'static':{'known_lookup_sites_in_range':6,
                      'known_lookup_sites_with_lw_opcode':6},
            'caller_linkage':{'linkage_confirmed':True},
            'execution':{'frame_layout':'a1_sp_plus_16',
                         'caller_jal_executed':True,
                         'caller_transfer_completed':True,
                         'builder_entry_reached':True,
                         'returned_to_caller':True, 'reason':'stop_pc'},
            'builder_execution':{
                'jr_ra_return_transfer_completed':True,
                'guest_execution_completed':True,
                'known_trig_lw_sites_executed':6,
                'known_trig_lw_sites_with_verified_packed_reads':6,
                'successful_packed_table_load_events_in_trace':6,
                'final_matrix_slots_written_by_sh':9,
                'final_matrix_slots_verified_against_static_sh_site':9,
                'matrix_slots':slots},
            'operation_schedule':{'guest_execution_completed':True,
                                  'matrix_slots':ops},
            'value_lineage':{'matrix_slots_with_observed_q12_lineage':9,
                             'matrix_slots':vals},
            'trig_address_provenance':{
                'packed_table_loads_with_provenance':6,
                'lookups_with_unknown_address_provenance':0}}


class MatrixIntegrityGateTests(unittest.TestCase):
    def test_all_ten_requirements_are_simultaneously_satisfied(self):
        summary=evaluate(**evidence())
        self.assertTrue(summary['synthetic_end_to_end_evidence_complete'])
        self.assertEqual(summary['requirements_total'],10)
        self.assertEqual(summary['requirements_satisfied'],10)
        self.assertEqual(summary['unmet_requirement_codes'],[])
        self.assertFalse(summary['original_gameplay_inputs_verified'])
        self.assertFalse(summary['original_playstation_matrix_values_compared'])
        self.assertFalse(summary['playable_native_switch_build_proven'])

    def test_no_caller_jal_or_frame_never_counts_as_full_path(self):
        for key in ('linkage_confirmed',):
            x=evidence();x['caller_linkage'][key]=False
            self.assertIn('caller_jal_and_a1_frame',evaluate(**x)['unmet_requirement_codes'])
        x=evidence();x['execution']['frame_layout']='separate_matrix'
        self.assertFalse(evaluate(**x)['checks']['caller_jal_and_a1_frame'])

    def test_missing_completed_jal_even_with_entry_reached(self):
        x=evidence();x['execution']['caller_transfer_completed']=False
        self.assertIn('executed_caller_to_builder_transfer',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_missing_jr_return_even_when_guest_completes(self):
        x=evidence();x['builder_execution']['jr_ra_return_transfer_completed']=False
        self.assertIn('executed_builder_to_caller_return',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_bounded_runner_ended_on_step_limit(self):
        x=evidence();x['execution']['reason']='step_limit'
        self.assertIn('bounded_guest_completed',evaluate(**x)['unmet_requirement_codes'])

    def test_static_sixth_lookup_word_missing(self):
        x=evidence();x['static']['known_lookup_sites_with_lw_opcode']=5
        self.assertIn('all_known_lookup_sites_present',evaluate(**x)['unmet_requirement_codes'])

    def test_sixth_site_not_reached_even_if_six_packed_load_events_exist(self):
        x=evidence();x['builder_execution']['known_trig_lw_sites_executed']=5
        self.assertIn('all_known_lookup_sites_executed_with_packed_lw',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_lookup_address_lineage_must_be_consistent(self):
        x=evidence();x['trig_address_provenance']['packed_table_loads_with_provenance']=5
        self.assertIn('address_provenance_for_all_lookups',
                      evaluate(**x)['unmet_requirement_codes'])
        x=evidence();x['trig_address_provenance']['lookups_with_unknown_address_provenance']=1
        self.assertIn('address_provenance_for_all_lookups',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_ninth_final_sh_not_a_verified_builder_site(self):
        x=evidence();x['builder_execution']['matrix_slots'][8]['final_sh_matches_static_a1_offset']=False
        self.assertIn('all_nine_final_sh_match_builder_sites',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_any_final_coefficient_without_packed_q12_value_lineage_fails(self):
        x=evidence();x['value_lineage']['matrix_slots_with_observed_q12_lineage']=8
        self.assertIn('all_nine_coefficients_retain_q12_lineage',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_disagreeing_shadow_reports_fail(self):
        x=evidence();x['operation_schedule']['matrix_slots'][2]['schedule']='not_written'
        self.assertIn('all_shadow_matrix_reports_agree',
                      evaluate(**x)['unmet_requirement_codes'])

    def test_partial_or_misindexed_slots_cannot_qualify(self):
        for change in ('truncate','swap'):
            x=evidence()
            if change=='truncate': x['builder_execution']['matrix_slots'].pop()
            else: x['builder_execution']['matrix_slots'][4]['slot_index']=8
            out=evaluate(**x)
            self.assertFalse(out['synthetic_end_to_end_evidence_complete'])
            self.assertIn('all_shadow_matrix_reports_agree',out['unmet_requirement_codes'])

    def test_unmet_reason_codes_are_stable_and_non_sensitive(self):
        x=evidence();x['static']['known_lookup_sites_in_range']=0
        x['execution']['returned_to_caller']=False
        out=evaluate(**x)
        self.assertEqual(out['unmet_requirement_codes'],[
            'executed_builder_to_caller_return', 'all_known_lookup_sites_present'])
        self.assertNotIn('0x',str(out))
        self.assertFalse(out['private_values_emitted'])

    def test_invalid_expected_counts_rejected(self):
        for kwargs in ({'expected_lookup_sites':0},{'expected_matrix_slots':0},
                       {'expected_matrix_slots':129}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                evaluate(**evidence(),**kwargs)

    def test_invalid_report_type_rejected(self):
        x=evidence();x['execution']=None
        with self.assertRaises(ValueError):evaluate(**x)

    def test_requirements_are_unique_and_explicit(self):
        self.assertEqual(len(REQUIREMENTS),len(set(REQUIREMENTS)))
        self.assertEqual(len(REQUIREMENTS),10)

if __name__=='__main__':unittest.main()
