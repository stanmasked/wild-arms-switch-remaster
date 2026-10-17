"""Synthetic-only privacy and arithmetic regressions for record address deltas."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_record_address_deltas import (
    SCHEMA, REPORT_SCHEMA, MAX_REFERENCE_BYTES, analyze, main,
)

SCALE = 2708
BASE = 0x80120000
OFFSET = 6


def fixture(indices=(0, 1, 5), *, base=BASE, offset=OFFSET,
            source='synthetic'):
    return {
        'schema': SCHEMA, 'source': source, 'site': 'site_1',
        'field_offset_s16': offset,
        'samples': [
            {'record_index': i,
             'global_base_u32': f'0x{base:08x}',
             'effective_address_u32':
                f'0x{((base + i*SCALE + offset) & 0xffffffff):08x}'}
            for i in indices
        ],
    }


class RecordAddressDeltasTests(unittest.TestCase):
    def test_three_distinct_indices_agree_with_two_independent_checks(self):
        report = analyze(fixture())
        self.assertTrue(report['agrees_with_checked_in_opcode_coefficient'])
        self.assertEqual(report['observations_checked'], 3)
        self.assertEqual(report['independent_index_pairs_checked'], 3)
        self.assertEqual(report['candidate_address_matches'], 3)
        self.assertEqual(report['index_delta_pairs_matching_opcode_coefficient'], 3)
        self.assertTrue(report['claimed_global_base_constant'])
        self.assertEqual(report['checked_in_opcode_coefficient'], 2708)
        self.assertFalse(report['record_size_verified'])
        self.assertFalse(report['original_executable_signature_checked'])

    def test_unsorted_indices_and_negative_field_offset(self):
        result = analyze(fixture(indices=(10, 0, 4), offset=-12))
        self.assertTrue(result['agrees_with_checked_in_opcode_coefficient'])
        self.assertEqual(result['independent_index_pairs_checked'], 3)

    def test_claim_of_external_capture_never_authenticates_source(self):
        result = analyze(fixture(source='external_ps1_capture_claim'))
        self.assertTrue(result['claimed_external_capture'])
        self.assertTrue(result['agrees_with_checked_in_opcode_coefficient'])
        self.assertFalse(result['authentic_ps1_capture_independently_verified'])
        self.assertFalse(result['runtime_memory_access_verified'])
        self.assertFalse(result['native_switch_build_verified'])

    def test_one_wrong_observed_effective_address_is_detected(self):
        data = fixture()
        wrong = int(data['samples'][1]['effective_address_u32'], 16) + 4
        data['samples'][1]['effective_address_u32'] = f'0x{wrong:08x}'
        result = analyze(data)
        self.assertFalse(result['agrees_with_checked_in_opcode_coefficient'])
        self.assertEqual(result['candidate_address_matches'], 2)
        self.assertLess(result['index_delta_pairs_matching_opcode_coefficient'], 3)

    def test_legacy_364_coefficient_rejected(self):
        data = fixture()
        for row in data['samples']:
            row['effective_address_u32'] = f'0x{BASE + row["record_index"]*364 + OFFSET:08x}'
        result = analyze(data)
        self.assertFalse(result['agrees_with_checked_in_opcode_coefficient'])
        self.assertEqual(result['candidate_address_matches'], 1)
        self.assertEqual(result['index_delta_pairs_matching_opcode_coefficient'], 0)

    def test_correct_slope_with_wrong_intercept_does_not_pass(self):
        data = fixture()
        for row in data['samples']:
            old = int(row['effective_address_u32'], 16)
            row['effective_address_u32'] = f'0x{old + 16:08x}'
        result = analyze(data)
        self.assertFalse(result['agrees_with_checked_in_opcode_coefficient'])
        self.assertEqual(result['candidate_address_matches'], 0)
        self.assertEqual(result['index_delta_pairs_matching_opcode_coefficient'], 3)

    def test_changing_base_between_observations_invalidates_relation(self):
        data = fixture()
        row = data['samples'][2]
        original_base = int(row['global_base_u32'], 16)
        row['global_base_u32'] = f'0x{original_base + 4:08x}'
        row['effective_address_u32'] = f'0x{BASE + 4 + 5*SCALE + OFFSET:08x}'
        result = analyze(data)
        self.assertFalse(result['claimed_global_base_constant'])
        self.assertFalse(result['agrees_with_checked_in_opcode_coefficient'])

    def test_32bit_wrap_or_alias_behavior_is_not_silently_accepted(self):
        data = fixture(indices=(0, 1, 2), base=0xffffff00, offset=0)
        result = analyze(data)
        self.assertFalse(result['no_32bit_address_wrap_required'])
        self.assertFalse(result['agrees_with_checked_in_opcode_coefficient'])
        self.assertFalse(result['record_size_verified'])

    def test_duplicate_or_two_indices_rejected(self):
        for indices in ((0, 0, 1), (0, 1), (1, 2, 2, 3)):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                analyze(fixture(indices=indices))

    def test_unknown_site_source_and_fields_rejected(self):
        for name, value in (
                ('site', 'site_4'), ('site', ['site_1']),
                ('source', 'verified_hardware'),
                ('schema', 'wrong'), ('field_offset_s16', True),
                ('field_offset_s16', 32768)):
            with self.subTest(field=name, value=value):
                sample = fixture()
                sample[name] = value
                with self.assertRaises(ValueError):
                    analyze(sample)
        sample = fixture()
        sample['some_private_field'] = 'PRIVATE_PC_0x80000000'
        with self.assertRaises(ValueError):
            analyze(sample)

    def test_private_address_field_types_and_index_limits_rejected(self):
        for field, value in (
                ('record_index', True), ('record_index', -1),
                ('record_index', 65536),
                ('global_base_u32', 0x80120000),
                ('global_base_u32', '0x8012000'),
                ('effective_address_u32', 'PRIVATE_ADDRESS_0x80120006')):
            with self.subTest(field=field, value=value):
                data = fixture()
                data['samples'][0][field] = value
                with self.assertRaises(ValueError):
                    analyze(data)

    def test_reference_size_and_bounded_sample_count(self):
        with self.assertRaises(ValueError):
            analyze(fixture(indices=tuple(range(129))))
        self.assertTrue(analyze(fixture(indices=tuple(range(128))))[
            'agrees_with_checked_in_opcode_coefficient'])

    def test_cli_matching_and_mismatching_have_no_private_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / 'PRIVATE_GUEST_RAM_0x80120000.json'
            private.write_text(json.dumps(fixture()))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([str(private)])
            self.assertEqual(code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['schema'], REPORT_SCHEMA)
            self.assertFalse(result['private_addresses_emitted'])
            self.assertNotIn('0x8012', output.getvalue())
            self.assertNotIn('PRIVATE_GUEST_RAM', output.getvalue())
            wrong = fixture()
            wrong['samples'][2]['effective_address_u32'] = '0x8012fefe'
            private.write_text(json.dumps(wrong))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([str(private)])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output.getvalue())[
                'agrees_with_checked_in_opcode_coefficient'])
            self.assertNotIn('0x8012', output.getvalue())

    def test_cli_malformed_and_missing_files_emit_generic_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / 'PRIVATE_POINTER_0x80120000.json'
            secret.write_text('{PRIVATE_REGISTER_CONTENTS')
            for filename in (secret, Path(tmp)/'MISSING_SECRET_GUEST_FILE.json'):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main([str(filename)])
                self.assertEqual(code, 2)
                report = json.loads(output.getvalue())
                self.assertEqual(report['error_code'], 'invalid_private_input')
                self.assertFalse(report['private_addresses_emitted'])
                self.assertNotIn('PRIVATE_', output.getvalue())
                self.assertNotIn('0x8012', output.getvalue())
                self.assertNotIn('Traceback', output.getvalue())

    def test_cli_oversized_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'PRIVATE_LARGE.json'
            p.write_bytes(b'{' + b'X' * MAX_REFERENCE_BYTES)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main([str(p)])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output.getvalue())['valid_input'], False)


if __name__ == '__main__':
    unittest.main()
