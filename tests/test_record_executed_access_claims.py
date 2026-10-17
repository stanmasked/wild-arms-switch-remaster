"""Synthetic PS-X EXE/claim correlation regressions, no original game data."""
import contextlib
import copy
import hashlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_verify_record_stride import three_signature_exe
from tests.test_record_pointer_use import (
    ADDU_V1_V1_V0, LW_A0_V1, word_at,
)
from tools.verify_record_stride import TARGETS
from tools.audit_record_executed_access_claims import (
    SCHEMA, REPORT_SCHEMA, _candidate_tail, analyze, main, MAX_REFERENCE_BYTES,
)

BASE = 0x80120000
INDICES = (0, 1, 5)
SCALE = 2708


def _hex(value):
    return f'0x{value:08x}'


def claim(sites=(0, 1), *, field_offsets=(0, 4),
          indices=INDICES, source='synthetic', extra_nop=False):
    """Create matched synthetic EXE and *claimed* instruction/address data."""
    data = three_signature_exe()
    for site_number, offset in zip(sites, field_offsets):
        site = TARGETS[site_number]
        word_at(data, site, 11, 0 if extra_nop else ADDU_V1_V1_V0)
        word_at(data, site, 12, ADDU_V1_V1_V0 if extra_nop else
                (LW_A0_V1 | (offset & 0xffff)))
        if extra_nop:
            word_at(data, site, 13, LW_A0_V1 | (offset & 0xffff))
    rows = []
    for site_number, offset in zip(sites, field_offsets):
        target = TARGETS[site_number]
        last = 13 if extra_nop else 12
        pcs = [_hex(target + 4 * i) for i in range(last + 1)]
        rows.append({
            'site': f'site_{site_number + 1}',
            'field_offset_s16': offset,
            'samples': [{
                'record_index': i,
                'global_base_u32': _hex(BASE),
                'effective_address_u32': _hex(BASE + SCALE * i + offset),
                'executed_pcs': list(pcs),
            } for i in indices],
        })
    return data, {
        'schema': SCHEMA, 'source': source,
        'exe_sha256': hashlib.sha256(data).hexdigest(),
        'observations': rows,
    }


class RecordExecutedAccessClaimsTests(unittest.TestCase):
    def test_two_site_three_index_correlation_is_still_only_claimed(self):
        exe, cap = claim()
        r = analyze(exe, cap)
        self.assertEqual(r['schema'], REPORT_SCHEMA)
        self.assertTrue(r['matched_ps_x_exe_sha256_claim'])
        self.assertTrue(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['signature_checked_sites'], 2)
        self.assertEqual(r['candidate_linear_memory_access_sites'], 2)
        self.assertEqual(r['claimed_execution_sequences_matching_static_code'], 6)
        self.assertEqual(r['claimed_execution_sequences_checked'], 6)
        self.assertEqual(r['cross_site_address_comparisons_matching'], 3)
        self.assertEqual(r['cross_site_address_comparisons_checked'], 3)
        self.assertFalse(r['actual_runtime_pc_provenance_authenticated'])
        self.assertFalse(r['original_ps1_hardware_execution_verified'])
        self.assertFalse(r['original_game_record_size_verified'])
        self.assertFalse(r['switch_build_verified'])

    def test_three_site_and_nonidentical_offsets(self):
        exe, cap = claim((0, 1, 2), field_offsets=(0, 4, 8))
        r = analyze(exe, cap)
        self.assertTrue(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_execution_sequences_checked'], 9)
        self.assertEqual(r['cross_site_address_comparisons_checked'], 9)

    def test_claimed_external_source_never_authenticates_debugger(self):
        exe, cap = claim(source='external_ps1_capture_claim')
        r = analyze(exe, cap)
        self.assertTrue(r['claimed_external_capture'])
        self.assertFalse(r['actual_runtime_pc_provenance_authenticated'])
        self.assertFalse(r['original_ps1_hardware_execution_verified'])

    def test_one_wrong_pc_in_declared_execution_sequence_is_rejected(self):
        exe, cap = claim()
        cap['observations'][0]['samples'][1]['executed_pcs'][11] = _hex(TARGETS[0]+48)
        r = analyze(exe, cap)
        self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_execution_sequences_matching_static_code'], 5)
        self.assertEqual(r['site_numeric_relationships_matching'], 2)

    def test_skipped_prefix_instruction_is_rejected(self):
        exe, cap = claim()
        pcs = cap['observations'][1]['samples'][0]['executed_pcs']
        pcs.pop(7)
        r = analyze(exe, cap)
        self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_execution_sequences_matching_static_code'], 5)

    def test_repeated_pc_refused_as_malformed_linear_claim(self):
        exe, cap = claim()
        pcs = cap['observations'][0]['samples'][0]['executed_pcs']
        pcs[2] = pcs[1]
        with self.assertRaisesRegex(ValueError, 'repeated instruction'):
            analyze(exe, cap)

    def test_wrong_field_displacement_never_matches_executable(self):
        exe, cap = claim()
        cap['observations'][1]['field_offset_s16'] = 8
        for row in cap['observations'][1]['samples']:
            row['effective_address_u32'] = _hex(
                BASE + SCALE * row['record_index'] + 8)
        r = analyze(exe, cap)
        self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['candidate_linear_memory_access_sites'], 1)

    def test_unknown_control_flow_and_memory_before_add_fail_closed(self):
        for inserted in (0x08000000, LW_A0_V1, 0x11090002):
            with self.subTest(inserted=inserted):
                exe, cap = claim()
                word_at(exe, TARGETS[0], 11, inserted)
                cap['exe_sha256'] = hashlib.sha256(exe).hexdigest()
                r = analyze(exe, cap)
                self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
                self.assertEqual(r['candidate_linear_memory_access_sites'], 1)

    def test_single_nop_before_add_is_accepted_when_pc_list_matches(self):
        exe, cap = claim(extra_nop=True)
        self.assertTrue(analyze(exe, cap)['claimed_data_consistent_with_checked_in_code'])

    def test_address_mismatch_refused_even_when_pc_sequence_matches(self):
        exe, cap = claim()
        cap['observations'][1]['samples'][2]['effective_address_u32'] = _hex(
            BASE + SCALE * 5 + 16)
        r = analyze(exe, cap)
        self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_execution_sequences_matching_static_code'], 6)
        self.assertLess(r['cross_site_address_comparisons_matching'], 3)

    def test_base_drift_between_sites_refuses_cross_site_correlation(self):
        exe, cap = claim()
        for row in cap['observations'][1]['samples']:
            row['global_base_u32'] = _hex(BASE + 16)
            row['effective_address_u32'] = _hex(BASE + 16 + SCALE *
                                               row['record_index'] + 4)
        r = analyze(exe, cap)
        self.assertFalse(r['claimed_base_constant_across_sites'])
        self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['site_numeric_relationships_matching'], 2)

    def test_missing_three_common_indices_is_not_multisite_evidence(self):
        exe, cap = claim(indices=(0, 1, 2, 3, 4, 5))
        cap['observations'][1]['samples'] = cap['observations'][1]['samples'][3:]
        cap['observations'][0]['samples'] = cap['observations'][0]['samples'][:3]
        with self.assertRaisesRegex(ValueError, 'insufficient overlapping'):
            analyze(exe, cap)

    def test_unaligned_word_access_does_not_correlate(self):
        exe, cap = claim(field_offsets=(0, 2))
        r = analyze(exe, cap)
        self.assertFalse(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_execution_sequences_matching_static_code'], 3)

    def test_modified_exe_or_wrong_sha_fail_before_claim(self):
        exe, cap = claim()
        exe[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            analyze(exe, cap)
        exe, cap = claim()
        exe[2048 + TARGETS[0] - 0x80011420] ^= 1
        cap['exe_sha256'] = hashlib.sha256(exe).hexdigest()
        with self.assertRaisesRegex(ValueError, 'index signature'):
            analyze(exe, cap)

    def test_invalid_site_repeated_site_and_bad_input_shape(self):
        exe, cap = claim()
        for mutation in ('duplicate', 'site_4', 'extra_field', 'bad_address',
                         'bad_index', 'bad_sha'):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(cap)
                if mutation == 'duplicate':
                    data['observations'][1]['site'] = 'site_1'
                elif mutation == 'site_4':
                    data['observations'][0]['site'] = 'site_4'
                elif mutation == 'extra_field':
                    data['observations'][0]['samples'][0]['private_pc'] = 'SECRET'
                elif mutation == 'bad_address':
                    data['observations'][0]['samples'][0]['executed_pcs'][0] = 'private'
                elif mutation == 'bad_index':
                    data['observations'][0]['samples'][0]['record_index'] = True
                else:
                    data['exe_sha256'] = 'A' * 64
                with self.assertRaises(ValueError):
                    analyze(exe, data)

    def test_exe_is_bounded_and_capture_has_at_least_two_sites(self):
        exe, cap = claim()
        with self.assertRaises(ValueError):
            analyze(exe[:2048], cap)
        data = copy.deepcopy(cap)
        data['observations'].pop()
        with self.assertRaises(ValueError):
            analyze(exe, data)
        data = copy.deepcopy(cap)
        data['observations'][0]['samples'] = data['observations'][0]['samples'][:2]
        with self.assertRaises(ValueError):
            analyze(exe, data)

    def test_cli_success_mismatch_and_sanitized_invalid_input(self):
        exe, capture = claim()
        with tempfile.TemporaryDirectory() as folder:
            inventory = Path(folder) / 'disc-inventory.json'
            inventory.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                 'size': len(exe), 'directory': False}]}))
            private = Path(folder) / 'PRIVATE_RAM_0x80120000.json'
            private.write_text(json.dumps(capture))
            def cli():
                output = io.StringIO()
                with patch('tools.audit_record_executed_access_claims.read_raw_iso_entry',
                           return_value=exe):
                    with contextlib.redirect_stdout(output):
                        status = main(['/private/game.bin', str(inventory), str(private)])
                return status, output.getvalue()

            code, output = cli()
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)['claimed_data_consistent_with_checked_in_code'])
            self.assertNotIn('PRIVATE_RAM', output)
            self.assertNotIn('0x8012', output)
            self.assertNotIn('0x8006', output)

            capture['observations'][0]['samples'][1]['effective_address_u32'] = _hex(
                BASE + SCALE + 4)
            private.write_text(json.dumps(capture))
            code, output = cli()
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)['claimed_data_consistent_with_checked_in_code'])
            self.assertNotIn('PRIVATE_RAM', output)

            private.write_text('{PRIVATE_REGISTERS_0x80120000')
            code, output = cli()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_REGISTERS', output)
            self.assertNotIn('/private/', output)

    def test_cli_missing_private_capture_does_not_emit_path(self):
        with tempfile.TemporaryDirectory() as folder:
            private = Path(folder) / 'PRIVATE_MISSING_SECRET_0x80010000.json'
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = main(['/private/game.bin', '/private/inventory.json',
                               str(private)])
            self.assertEqual(status, 2)
            self.assertNotIn('/private', out.getvalue())
            self.assertNotIn('Traceback', out.getvalue())
            self.assertFalse(json.loads(out.getvalue())[
                'private_addresses_or_game_bytes_emitted'])

    def test_reference_file_size_cap(self):
        self.assertEqual(MAX_REFERENCE_BYTES, 256 * 1024)
        with tempfile.TemporaryDirectory() as folder:
            inv = Path(folder) / 'inv.json'
            inv.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'lba': 0, 'size': 2048}]}))
            capture = Path(folder) / 'PRIVATE_TOO_LARGE'
            capture.write_bytes(b'{' + b'X' * MAX_REFERENCE_BYTES)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = main(['/private/game.bin', str(inv), str(capture)])
            self.assertEqual(status, 2)
            self.assertNotIn('PRIVATE_TOO_LARGE', out.getvalue())


if __name__ == '__main__':
    unittest.main()
