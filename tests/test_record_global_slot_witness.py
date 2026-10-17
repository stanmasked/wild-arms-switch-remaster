"""Synthetic-only tests for PS1 opcode-derived global pointer slot witnesses."""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_pipeline_coupling import example, _hex, BASE
from tools.audit_record_pipeline_coupling import analyze as previous_analyze
from tools.audit_record_global_slot_witness import (
    SCHEMA, REPORT_SCHEMA, _global_slot_opcode_address, analyze, main,
)
from tools.verify_record_stride import GLOBAL_WORDS, TARGETS


def fixture(*, sites=(0, 1)):
    exe, joined = example(sites=sites)
    witnesses = []
    for sample in joined['pipeline_samples']:
        site = TARGETS[int(sample['site'][-1]) - 1]
        sample['initial_gprs_u32']['3'] = '0x800d0000'
        witnesses.append({
            'site': sample['site'],
            'record_index': sample['record_index'],
            'global_lw_pc_u32': _hex(site + 9 * 4),
            'lui_base_u32': '0x800d0000',
            'effective_slot_address_u32': '0x800d2c3c',
            'slot_memory_word_u32': _hex(BASE),
        })
    return exe, {
        'schema': SCHEMA, 'joined_claim': joined,
        'slot_witnesses': witnesses,
    }


class GlobalSlotWitnessTests(unittest.TestCase):
    def test_exact_lui_and_lw_derive_source_without_input_pointer(self):
        words = [0] * 8 + list(GLOBAL_WORDS)
        self.assertEqual(_global_slot_opcode_address(words),
                         (0x800d0000, 0x800d2c3c))

    def test_two_sites_six_memory_witnesses_are_only_claimed(self):
        exe, reference = fixture()
        result = analyze(exe, reference)
        self.assertEqual(result['schema'], REPORT_SCHEMA)
        self.assertEqual(result['unique_exe_global_slot_sources_checked'], 2)
        self.assertEqual(result['private_site_index_witnesses_checked'], 6)
        self.assertEqual(result['private_slot_witnesses_matching_exe_source'], 6)
        self.assertTrue(result['prior_branch_pipeline_claims_consistent'])
        self.assertTrue(result['all_private_global_slot_claims_consistent'])
        self.assertFalse(result['original_game_slot_memory_independently_observed'])
        self.assertFalse(result['authentic_ps1_trace_verified'])
        self.assertFalse(result['hardware_pipeline_cycle_accuracy_verified'])
        self.assertFalse(result['original_game_record_size_verified'])
        self.assertFalse(result['nintendo_switch_build_verified'])
        self.assertFalse(result['private_memory_values_or_addresses_emitted'])
        self.assertNotIn('0x800d', str(result))
        self.assertNotIn('0x8012', str(result))

    def test_three_code_sites_nine_witnesses(self):
        exe, reference = fixture(sites=(0, 1, 2))
        result = analyze(exe, reference)
        self.assertTrue(result['all_private_global_slot_claims_consistent'])
        self.assertEqual(result['unique_exe_global_slot_sources_checked'], 3)
        self.assertEqual(result['private_slot_witnesses_matching_exe_source'], 9)

    def test_prior_joined_trace_remains_valid_with_exe_derived_base(self):
        exe, reference = fixture()
        result = previous_analyze(exe, reference['joined_claim'])
        self.assertTrue(result['joined_private_claims_consistent'])

    def test_one_wrong_claimed_slot_word_only_invalidates_that_witness(self):
        exe, reference = fixture()
        reference['slot_witnesses'][1]['slot_memory_word_u32'] = '0x80120010'
        result = analyze(exe, reference)
        self.assertFalse(result['all_private_global_slot_claims_consistent'])
        self.assertEqual(result['private_slot_witnesses_matching_exe_source'], 5)
        self.assertTrue(result['prior_branch_pipeline_claims_consistent'])

    def test_arbitrary_v1_source_now_rejected(self):
        exe, reference = fixture()
        sample = reference['joined_claim']['pipeline_samples'][0]
        sample['initial_gprs_u32']['3'] = '0x80130000'
        result = analyze(exe, reference)
        self.assertFalse(result['all_private_global_slot_claims_consistent'])
        # Stage 239 checked only the *claimed LW result*, not that its
        # originating register actually pointed at the EXE's LUI/LW slot.
        self.assertTrue(result['prior_branch_pipeline_claims_consistent'])

    def test_wrong_slot_address_or_base_or_load_pc_is_refused(self):
        for field, replacement in (
                ('effective_slot_address_u32', '0x800d2c40'),
                ('lui_base_u32', '0x80130000'),
                ('global_lw_pc_u32', '0x8006d280')):
            with self.subTest(field=field):
                exe, reference = fixture()
                reference['slot_witnesses'][0][field] = replacement
                result = analyze(exe, reference)
                self.assertFalse(result['all_private_global_slot_claims_consistent'])
                self.assertEqual(result['private_slot_witnesses_matching_exe_source'], 5)

    def test_physical_alias_is_not_implicitly_attested_as_same_virtual_source(self):
        exe, reference = fixture()
        reference['slot_witnesses'][0]['effective_slot_address_u32'] = '0xa00d2c3c'
        result = analyze(exe, reference)
        self.assertFalse(result['all_private_global_slot_claims_consistent'])
        self.assertEqual(result['private_slot_witnesses_matching_exe_source'], 5)

    def test_missing_duplicate_and_foreign_slot_samples_are_refused(self):
        for choice in ('missing', 'duplicate', 'foreign'):
            with self.subTest(choice=choice):
                exe, reference = fixture()
                witnesses = reference['slot_witnesses']
                if choice == 'missing':
                    witnesses.pop()
                elif choice == 'duplicate':
                    witnesses[-1]['record_index'] = witnesses[0]['record_index']
                    witnesses[-1]['site'] = witnesses[0]['site']
                else:
                    witnesses[-1]['site'] = 'site_4'
                # A missing sample may fail the strict 6..96 count
                # guard before the exact site/index coverage check.
                with self.assertRaisesRegex(
                        ValueError, 'bounded|coverage|duplicate|foreign'):
                    analyze(exe, reference)

    def test_injected_memory_dump_and_bad_index_are_refused(self):
        for choice in ('extra', 'boolean-index', 'bad-word'):
            with self.subTest(choice=choice):
                exe, reference = fixture()
                witness = reference['slot_witnesses'][0]
                if choice == 'extra':
                    witness['PRIVATE_RAM_DUMP'] = 'secret'
                elif choice == 'boolean-index':
                    witness['record_index'] = True
                else:
                    witness['slot_memory_word_u32'] = 'PRIVATE_RAM_0x80120000'
                with self.assertRaises(ValueError):
                    analyze(exe, reference)

    def test_opcode_source_mutation_is_not_accepted_as_valid_original_signature(self):
        exe, reference = fixture()
        pc = TARGETS[0]
        offset = 2048 + pc - 0x80011420 + 8 * 4
        exe[offset] ^= 1
        reference['joined_claim']['access_claim']['exe_sha256'] = (
            hashlib.sha256(exe).hexdigest())
        with self.assertRaises(ValueError):
            analyze(exe, reference)

    def test_direct_decoder_rejects_unrelated_lui_or_lw_and_bad_alignment(self):
        words = [0] * 8 + list(GLOBAL_WORDS)
        for which, word in ((8, 0x3c02800d), (9, 0x8c642c3c),
                            (9, 0x8c632c3d)):
            with self.subTest(which=which, word=word):
                data = words.copy()
                data[which] = word
                with self.assertRaises(ValueError):
                    _global_slot_opcode_address(data)

    def test_external_capture_label_still_does_not_prove_authenticity(self):
        exe, reference = fixture()
        reference['joined_claim']['access_claim']['source'] = (
            'external_ps1_capture_claim')
        result = analyze(exe, reference)
        self.assertTrue(result['all_private_global_slot_claims_consistent'])
        self.assertFalse(result['original_game_slot_memory_independently_observed'])
        self.assertFalse(result['authentic_ps1_trace_verified'])

    def test_private_cli_success_disagreement_and_corruption_are_sanitized(self):
        exe, reference = fixture()
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / 'inventory.json'
            inventory.write_text(json.dumps({'entries': [{
                'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                'size': len(exe), 'directory': False}]}))
            private = Path(directory) / 'PRIVATE_SLOT_0x800d2c3c.json'
            private.write_text(json.dumps(reference))

            def run_cli():
                output = io.StringIO()
                with patch(
                        'tools.audit_record_global_slot_witness.read_raw_iso_entry',
                        return_value=exe):
                    with contextlib.redirect_stdout(output):
                        status = main(['/private/game.bin',
                                       str(inventory), str(private)])
                return status, output.getvalue()

            code, output = run_cli()
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)['schema'], REPORT_SCHEMA)
            for secret in ('PRIVATE_SLOT', '0x800d', '0x8012', '/private'):
                self.assertNotIn(secret, output)
            reference['slot_witnesses'][1]['slot_memory_word_u32'] = '0x00000000'
            private.write_text(json.dumps(reference))
            code, output = run_cli()
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)['all_private_global_slot_claims_consistent'])
            self.assertNotIn('0x800d', output)
            private.write_text('{PRIVATE_REGISTER_CONTENT_0x80120000')
            code, output = run_cli()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_REGISTER', output)
            self.assertNotIn('Traceback', output)

    def test_missing_private_file_does_not_expose_local_file_path(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / 'PRIVATE_SECRET_PATH_0x80120000'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['/private/game.bin', '/private/inventory.json',
                             str(private)])
            self.assertEqual(code, 2)
            self.assertNotIn('PRIVATE_SECRET_PATH', output.getvalue())
            self.assertNotIn('/private/', output.getvalue())


if __name__ == '__main__':
    unittest.main()
