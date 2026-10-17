"""Synthetic-only tests coupling PS1 EXE/PC claims to delayed LW predicates."""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_executed_access_claims import claim, _hex, BASE, SCALE
from tests.test_record_pointer_use import ADDU_V1_V1_V0, LW_A0_V1, word_at
from tests.test_record_base_provenance import branch
from tools.verify_record_stride import TARGETS
from tools.audit_record_pipeline_coupling import SCHEMA, REPORT_SCHEMA, analyze, main
from tools.audit_record_branch_access_claims import analyze as stage237
from tools.audit_mips_load_delay_predicates import analyze as stage238

GLOBAL_SLOT = 0x80130000


def example(*, sites=(0, 1), op=5, rt=0):
    exe, access = claim(sites=sites, field_offsets=tuple(4*i for i in sites))
    pipeline = []
    for group in access['observations']:
        site_num = int(group['site'][-1]) - 1
        site_pc = TARGETS[site_num]
        offset = group['field_offset_s16']
        word_at(exe, site_pc, 11, branch(op, 3, rt, 3))
        word_at(exe, site_pc, 12, 0)
        word_at(exe, site_pc, 15, ADDU_V1_V1_V0)
        word_at(exe, site_pc, 16, LW_A0_V1 | (offset & 0xffff))
        for row in group['samples']:
            index = row['record_index']
            row['executed_pcs'] = [
                _hex(site_pc + 4*i) for i in list(range(13)) + [15, 16]]
            registers = {
                '2': _hex(677 * index),
                '3': _hex(GLOBAL_SLOT),
            }
            if rt == 8:
                registers['8'] = _hex(0)
            pipeline.append({
                'site': group['site'],
                'record_index': index,
                'initial_gprs_u32': registers,
                'lw_results_u32': {
                    _hex(site_pc+9*4): _hex(BASE),
                    _hex(site_pc+16*4): _hex(0x21),
                },
            })
    access['exe_sha256'] = hashlib.sha256(exe).hexdigest()
    return exe, {'schema': SCHEMA, 'access_claim': access,
                 'pipeline_samples': pipeline}


class CoupledBranchLoadTests(unittest.TestCase):
    def test_two_sites_six_samples_agree_across_both_oracles(self):
        exe, joined = example()
        result = analyze(exe, joined)
        self.assertTrue(result['joined_private_claims_consistent'])
        self.assertTrue(result['stage237_exe_address_claims_consistent'])
        self.assertEqual(result['sites_checked'], 2)
        self.assertEqual(result['joined_site_index_samples_checked'], 6)
        self.assertEqual(result['joint_branch_load_samples_matching'], 6)
        self.assertEqual(result['claimed_branch_predicates_matching'], 6)
        self.assertEqual(result['claimed_lw_values_bound_to_exe_opcodes'], 12)
        self.assertFalse(result['original_ps1_trace_authenticated'])
        self.assertFalse(result['hardware_cycle_accurate_pipeline_verified'])
        self.assertFalse(result['original_game_record_size_verified'])
        self.assertFalse(result['native_switch_build_verified'])
        self.assertFalse(result['private_data_emitted'])

    def test_three_sites_and_nine_samples_match(self):
        exe, joined = example(sites=(0, 1, 2))
        r = analyze(exe, joined)
        self.assertEqual(r['sites_checked'], 3)
        self.assertEqual(r['joined_site_index_samples_checked'], 9)
        self.assertTrue(r['joined_private_claims_consistent'])

    def test_previous_stage237_still_checks_same_exe_and_address_claims(self):
        exe, joined = example()
        r = stage237(exe, joined['access_claim'])
        self.assertTrue(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_execution_sequences_checked'], 6)
        self.assertEqual(r['cross_site_address_comparisons_matching'], 3)

    def test_one_wrong_loaded_global_pointer_breaks_one_joint_sample(self):
        exe, joined = example()
        first = joined['pipeline_samples'][0]
        key = _hex(TARGETS[0]+36)
        first['lw_results_u32'][key] = _hex(BASE + 16)
        r = analyze(exe, joined)
        self.assertFalse(r['joined_private_claims_consistent'])
        self.assertEqual(r['joint_branch_load_samples_matching'], 5)
        self.assertTrue(r['stage237_exe_address_claims_consistent'])

    def test_mismatched_pre_sll_index_is_rejected_even_when_pcs_match(self):
        exe, joined = example()
        joined['pipeline_samples'][1]['initial_gprs_u32']['2'] = _hex(677*5)
        r = analyze(exe, joined)
        self.assertFalse(r['joined_private_claims_consistent'])
        self.assertEqual(r['joint_branch_load_samples_matching'], 5)

    def test_branch_register_snapshot_changes_predicate(self):
        exe, joined = example(rt=8)
        self.assertTrue(analyze(exe, joined)['joined_private_claims_consistent'])
        # BEQ v1,t0 (equal) claimed taken; t0 not equal makes it false.
        for group in joined['access_claim']['observations']:
            site = TARGETS[int(group['site'][-1])-1]
            word_at(exe, site, 11, branch(4, 3, 8, 3))
        joined['access_claim']['exe_sha256'] = hashlib.sha256(exe).hexdigest()
        for sample in joined['pipeline_samples']:
            sample['initial_gprs_u32']['8'] = _hex(BASE)
        self.assertTrue(analyze(exe, joined)['joined_private_claims_consistent'])
        joined['pipeline_samples'][0]['initial_gprs_u32']['8'] = _hex(0)
        r = analyze(exe, joined)
        self.assertFalse(r['joined_private_claims_consistent'])
        self.assertEqual(r['joint_branch_load_samples_matching'], 5)

    def test_missing_pipeline_site_index_fails_closed(self):
        exe, joined = example()
        joined['pipeline_samples'].pop()
        with self.assertRaisesRegex(ValueError, 'coverage|count'):
            analyze(exe, joined)

    def test_duplicate_or_foreign_pipeline_site_index_is_rejected(self):
        for mutation in ('duplicate', 'foreign', 'unknown-site'):
            with self.subTest(mutation=mutation):
                exe, joined = example()
                if mutation == 'duplicate':
                    joined['pipeline_samples'][-1]['record_index'] = 0
                elif mutation == 'foreign':
                    joined['pipeline_samples'][-1]['record_index'] = 100
                else:
                    joined['pipeline_samples'][-1]['site'] = 'site_4'
                with self.assertRaisesRegex(ValueError, 'foreign|duplicate'):
                    analyze(exe, joined)

    def test_injected_claim_fields_not_used_as_untrusted_runtime_data(self):
        exe, joined = example()
        joined['pipeline_samples'][0]['PRIVATE_DUMP'] = 'RAM_SECRET'
        with self.assertRaisesRegex(ValueError, 'pipeline fields'):
            analyze(exe, joined)

    def test_extra_missing_or_noncanonical_lw_result_rejected(self):
        for mutation in ('extra', 'missing', 'uppercase'):
            with self.subTest(mutation=mutation):
                exe, joined = example()
                results = joined['pipeline_samples'][0]['lw_results_u32']
                original = _hex(TARGETS[0]+36)
                if mutation == 'extra':
                    results['0x80010000'] = _hex(1)
                elif mutation == 'missing':
                    results.pop(original)
                else:
                    results[original.upper().replace('0X', '0x')] = results.pop(original)
                with self.assertRaisesRegex(ValueError, 'LW capture shape'):
                    analyze(exe, joined)

    def test_false_branch_pc_claim_cannot_be_rescued_by_registers(self):
        exe, joined = example()
        pcs = joined['access_claim']['observations'][0]['samples'][0]['executed_pcs']
        pcs[13] = _hex(TARGETS[0]+14*4)
        r = analyze(exe, joined)
        self.assertFalse(r['stage237_exe_address_claims_consistent'])
        self.assertFalse(r['joined_private_claims_consistent'])

    def test_private_exe_hash_mismatch_is_fail_closed(self):
        exe, joined = example()
        exe[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            analyze(exe, joined)

    def test_original_source_label_never_authenticates_runtime(self):
        exe, joined = example()
        joined['access_claim']['source'] = 'external_ps1_capture_claim'
        r = analyze(exe, joined)
        self.assertTrue(r['joined_private_claims_consistent'])
        self.assertFalse(r['original_ps1_trace_authenticated'])
        self.assertFalse(r['hardware_cycle_accurate_pipeline_verified'])

    def test_legacy_stage238_claim_remains_usable_independently(self):
        from tests.test_audit_mips_load_delay_predicates import fixture
        r = stage238(fixture())
        self.assertTrue(r['synthetic_or_claimed_trace_self_consistent'])
        self.assertFalse(r['game_record_layout_verified'])

    def test_expected_final_lw_address_is_checked_privately(self):
        from tests.test_audit_mips_load_delay_predicates import fixture
        # Existing independent model can bind an expected *last* LW only
        # when the trace actually ends with a supported memory instruction.
        with self.assertRaisesRegex(ValueError, 'expected final LW'):
            stage238(fixture(), expected_final_lw_access_u32=BASE)

    def test_bad_or_unaligned_initial_load_slot_pointer_fails_jointly(self):
        exe, joined = example()
        joined['pipeline_samples'][0]['initial_gprs_u32']['3'] = _hex(
            GLOBAL_SLOT + 2)
        r = analyze(exe, joined)
        self.assertFalse(r['joined_private_claims_consistent'])
        self.assertEqual(r['joint_branch_load_samples_matching'], 5)

    def test_cli_valid_mismatch_and_bad_private_json_are_sanitized(self):
        exe, joined = example()
        with tempfile.TemporaryDirectory() as directory:
            inv = Path(directory)/'inventory.json'
            inv.write_text(json.dumps({'entries': [{
                'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                'size': len(exe), 'directory': False}]}))
            private = Path(directory)/'PRIVATE_RAM_0x80120000.json'
            private.write_text(json.dumps(joined))
            def run_cli():
                out = io.StringIO()
                with patch('tools.audit_record_pipeline_coupling.read_raw_iso_entry',
                           return_value=exe):
                    with contextlib.redirect_stdout(out):
                        status = main(['/private/game.bin', str(inv), str(private)])
                return status, out.getvalue()

            status, output = run_cli()
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output)['schema'], REPORT_SCHEMA)
            self.assertNotIn('PRIVATE_RAM', output)
            self.assertNotIn('0x8012', output)
            self.assertNotIn('0x8006', output)
            joined['pipeline_samples'][0]['initial_gprs_u32']['2'] = _hex(677*5)
            private.write_text(json.dumps(joined))
            status, output = run_cli()
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(output)['joined_private_claims_consistent'])
            private.write_text('{PRIVATE_REGISTERS_0x80000000')
            status, output = run_cli()
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_REGISTERS', output)
            self.assertNotIn('/private/', output)

    def test_missing_private_file_never_emits_input_path(self):
        with tempfile.TemporaryDirectory() as path:
            secret = Path(path)/'PRIVATE_MISSING_0x80010000'
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(['/private/game.bin', '/private/inventory.json',
                             str(secret)])
            self.assertEqual(code, 2)
            self.assertNotIn('PRIVATE_MISSING', out.getvalue())
            self.assertNotIn('Traceback', out.getvalue())


if __name__ == '__main__':
    unittest.main()
