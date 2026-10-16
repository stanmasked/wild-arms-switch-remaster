"""End-to-end synthetic PS-X EXE reference attribution of mismatched arithmetic."""
import json
from pathlib import Path
import tempfile
import contextlib
from io import StringIO
import unittest

from tools.mips_ps1_matrix_reference import compare
from tools.audit_ps1_matrix_reference import main as verify_cli
from tools.mips_ps1_capture_pack import pack
from tools.audit_ps1_capture_pack import main as pack_cli
from tests.test_ps1_arithmetic_capture import synthetic_builder, capture_inputs
from tests.test_mips_ps1_matrix_reference import MATRIX


class AttributionIntegrationTests(unittest.TestCase):
    def test_stage219_nine_matrix_coefficients_keep_separate_root_candidates(self):
        blob,fixture,events=synthetic_builder()
        events['events'][0]['result_u32']=12
        events['events'][20]['result_u32']=16
        fixture['expected_arithmetic_events']=events
        fixture['require_arithmetic_events']=True
        out=compare(blob,fixture)
        self.assertTrue(out['matches_supplied_nine_coefficients'])
        self.assertFalse(out['matches_complete_reference'])
        self.assertEqual(out['arithmetic_matrix_attribution']['candidate_affected_slot_indices'],[0,5])
        self.assertEqual(out['arithmetic_matrix_attribution']['matrix_slots'][0]['candidate_mismatch_event_indices'],[0])
        self.assertEqual(out['arithmetic_matrix_attribution']['matrix_slots'][5]['candidate_mismatch_event_indices'],[20])

    def test_unrelated_hi_mismatch_not_blame_on_nine_mflo_based_coefficients(self):
        blob,fixture,events=synthetic_builder()
        events['events'][0]['secondary_u32']=123
        fixture['expected_arithmetic_events']=events
        out=compare(blob,fixture)
        self.assertEqual(out['arithmetic_events']['secondary_result_mismatch_indices'],[0])
        self.assertEqual(out['arithmetic_matrix_attribution']['candidate_affected_slot_indices'],[])
        self.assertEqual(out['arithmetic_matrix_attribution']['mismatching_events_without_final_matrix_dependency'],[0])

    def test_one_multiply_with_both_halves_wrong_is_one_event_in_summary(self):
        blob,fixture,events=synthetic_builder()
        entry=events['events'][0]
        entry['result_u32']=(entry['result_u32']+1)&0xffffffff
        entry['secondary_u32']=(entry['secondary_u32']+1)&0xffffffff
        fixture['expected_arithmetic_events']=events
        fixture['require_arithmetic_events']=True
        out=compare(blob,fixture)
        comparison=out['arithmetic_events']
        self.assertEqual(comparison['mismatching_event_indices'],[0])
        self.assertEqual(comparison['result_value_mismatch_indices'],[0])
        self.assertEqual(comparison['secondary_result_mismatch_indices'],[0])
        self.assertEqual(comparison['matching_event_count'],
                         comparison['executed_event_count']-1)
        self.assertEqual(out['arithmetic_matrix_attribution']['matrix_slots'][0]
                         ['candidate_primary_mismatch_indices'],[0])
        self.assertFalse(out['arithmetic_matrix_attribution']['proven_numeric_causation'])
        self.assertNotIn('result_u32',str(out))

    def test_false_site_alignment_cannot_generate_slot_causation(self):
        blob,fixture,events=synthetic_builder()
        events['events'][0]['pc']=events['events'][1]['pc']
        fixture['expected_arithmetic_events']=events
        report=compare(blob,fixture)['arithmetic_matrix_attribution']
        self.assertFalse(report['attribution_performed'])
        self.assertEqual(report['reason_code'],'arithmetic_event_alignment_failed')

    def test_optional_reference_does_not_change_overall_numerical_match(self):
        blob,fixture,events=synthetic_builder()
        events['events'][2]['result_u32']=123
        fixture['expected_arithmetic_events']=events
        out=compare(blob,fixture)
        self.assertTrue(out['matches_complete_reference'])
        self.assertEqual(out['arithmetic_matrix_attribution']['candidate_affected_slot_indices'],[0])

    def test_no_independent_reference_no_attribution(self):
        blob,fixture,_=synthetic_builder()
        out=compare(blob,fixture)
        self.assertIsNone(out['arithmetic_matrix_attribution'])
        self.assertIsNone(out['arithmetic_events'])

    def test_incomplete_guest_does_not_guess_impacted_coefficients(self):
        blob,fixture,events=synthetic_builder()
        fixture['expected_arithmetic_events']=events
        fixture['max_steps']=5
        report=compare(blob,fixture)['arithmetic_matrix_attribution']
        self.assertFalse(report['attribution_performed'])
        self.assertEqual(report['candidate_affected_slot_indices'],[])

    def test_private_reference_cli_prints_only_indices(self):
        blob,fixture,events=synthetic_builder()
        events['events'][8]['result_u32']=123
        fixture['expected_arithmetic_events']=events
        fixture['require_arithmetic_events']=True
        with tempfile.TemporaryDirectory() as td:
            exe,ref=Path(td)/'exe',Path(td)/'ref.json'
            exe.write_bytes(blob);ref.write_text(json.dumps(fixture))
            out=StringIO()
            with contextlib.redirect_stdout(out):
                code=verify_cli(['--exe',str(exe),'--reference',str(ref)])
            report=json.loads(out.getvalue())
            self.assertEqual(code,1)
            self.assertEqual(report['arithmetic_matrix_attribution']['candidate_affected_slot_indices'],[2])
            self.assertNotIn('result_u32',out.getvalue())
            self.assertNotIn('0x8001',out.getvalue())

    def test_packer_cli_emits_attribution_only_when_external_log_supplied(self):
        blob,fixture,events=synthetic_builder()
        before,after,ram0,ram1=capture_inputs(blob,fixture)
        events['events'][4]['result_u32']=999
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            files=[root/f for f in ('game.exe','before.json','after.json','before.ram','after.ram','arith.json','ref.json')]
            files[0].write_bytes(blob)
            files[1].write_text(json.dumps(before))
            files[2].write_text(json.dumps(after))
            files[3].write_bytes(ram0)
            files[4].write_bytes(ram1)
            files[5].write_text(json.dumps(events))
            args=['--exe',str(files[0]),'--before-registers',str(files[1]),
                  '--after-registers',str(files[2]),'--before-ram',str(files[3]),
                  '--after-ram',str(files[4]),'--ram-base',hex(MATRIX),
                  '--arithmetic-events',str(files[5]),'--require-arithmetic-events',
                  '--output',str(files[6]),'--synthetic','--compare']
            output=StringIO()
            with contextlib.redirect_stdout(output):status=pack_cli(args)
            self.assertEqual(status,1)
            report=json.loads(output.getvalue())
            self.assertEqual(report['arithmetic_matrix_attribution']['candidate_affected_slot_indices'],[1])
            self.assertFalse(report['matches_complete_reference'])
            self.assertNotIn('result_u32',output.getvalue())
            self.assertTrue(files[6].exists())

    def test_conservative_labels_not_hardware_proof(self):
        blob,fixture,events=synthetic_builder()
        fixture['expected_arithmetic_events']=events
        out=compare(blob,fixture)['arithmetic_matrix_attribution']
        self.assertFalse(out['proven_numeric_causation'])
        self.assertFalse(out['original_gameplay_equivalence_proven'])
        self.assertTrue(out['synthetic_dynamic_dependency_only'])


if __name__=='__main__':unittest.main()
