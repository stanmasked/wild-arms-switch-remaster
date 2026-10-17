"""Synthetic-only tests for claimed PS1 debugger provenance and receipts."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_capture_stream_binding import (
    payload, refresh, _encode, _sha,
)
from tools.audit_record_capture_provenance import (
    SCHEMA, RECEIPT_SCHEMA, REPORT_SCHEMA, MAX_PROVENANCE_BYTES,
    MAX_RECEIPT_BYTES, analyze, main,
)

NONCE = '0123456789abcdeffedcba9876543210'


def fixture():
    exe, temporal, binding, rows, streams = payload()
    return pack(exe, temporal, binding, streams), rows


def pack(exe, temporal, binding, streams, *, nonce=NONCE, conditions=None):
    binding_raw = _encode(binding)
    provenance = {
        'schema': SCHEMA,
        'session_nonce': nonce,
        'stream_binding_manifest_sha256': _sha(binding_raw),
        'debugger': {
            'name': 'synthetic_debugger',
            'version': '0.1.0-test',
            'binary_sha256': 'a' * 64,
            'platform': 'linux-x86_64',
        },
        'capture_conditions': conditions or {
            'target_kind': 'emulator',
            'cpu_backend': 'interpreter',
            'event_clock': 'debugger-counter',
            'sample_mode': 'halted-breakpoint',
        },
    }
    provenance_raw = _encode(provenance)
    receipts = {}
    for role in ('before', 'after'):
        lines = [json.loads(line) for line in streams[role].splitlines()]
        receipts[role] = {
            'schema': RECEIPT_SCHEMA, 'role': role,
            'session_nonce': nonce,
            'collector_tag': next(s['collector_tag'] for s in binding['streams']
                                  if s['role'] == role),
            'provenance_sha256': _sha(provenance_raw),
            'stream_sha256': _sha(streams[role]),
            'observed_rows': len(lines),
            'first_event_sequence': lines[0]['event_sequence'],
            'last_event_sequence': lines[-1]['event_sequence'],
        }
    return (exe, temporal, binding_raw, streams['before'], streams['after'],
            provenance_raw, _encode(receipts['before']),
            _encode(receipts['after']))


def run(p):
    return analyze(*p)


def edit_json(p, position, change):
    values = list(p)
    obj = json.loads(values[position])
    change(obj)
    values[position] = _encode(obj)
    return tuple(values)


class CaptureProvenanceTests(unittest.TestCase):
    def test_valid_private_claims_bind_both_receipts(self):
        p, _ = fixture()
        r = run(p)
        self.assertEqual(r['schema'], REPORT_SCHEMA)
        self.assertTrue(r['all_supplied_provenance_claims_consistent'])
        self.assertTrue(r['exact_stream_binding_manifest_checked'])
        self.assertTrue(r['session_nonce_matches_both_receipts'])
        self.assertEqual(r['collector_receipts_bound_to_raw_streams'], 2)
        self.assertEqual(r['claimed_capture_rows_checked'], 12)
        for key in ('debugger_binary_independently_verified',
                    'capture_conditions_independently_observed',
                    'collector_receipts_cryptographically_authenticated',
                    'session_origin_independently_authenticated',
                    'original_ps1_execution_verified',
                    'original_game_record_size_verified',
                    'native_switch_game_build_verified',
                    'private_hashes_addresses_or_values_emitted'):
            self.assertFalse(r[key])
        self.assertNotIn(NONCE, str(r))
        self.assertNotIn('synthetic_debugger', str(r))

    def test_claim_of_real_hardware_never_proves_original_execution(self):
        p, _ = fixture()
        changed = edit_json(p, 5, lambda x: x['capture_conditions'].update(
            target_kind='hardware', cpu_backend='unknown'))
        # Recreate the receipts so all claimed hashes agree.
        values = list(changed)
        for pos in (6, 7):
            receipt = json.loads(values[pos])
            receipt['provenance_sha256'] = _sha(values[5])
            values[pos] = _encode(receipt)
        result = run(tuple(values))
        self.assertTrue(result['all_supplied_provenance_claims_consistent'])
        self.assertFalse(result['original_ps1_execution_verified'])

    def test_wrong_session_nonce_in_one_receipt_rejected(self):
        p, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            run(edit_json(p, 7, lambda x: x.update(session_nonce='f' * 32)))

    def test_swapped_receipts_rejected(self):
        p, _ = fixture()
        values = list(p)
        values[6], values[7] = values[7], values[6]
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            run(tuple(values))

    def test_changed_debugger_version_without_new_receipts_rejected(self):
        p, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            run(edit_json(p, 5, lambda x: x['debugger'].update(version='9.9.9')))

    def test_changed_capture_conditions_without_new_receipts_rejected(self):
        p, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            run(edit_json(p, 5, lambda x: x['capture_conditions'].update(
                sample_mode='step-then-sample')))

    def test_wrong_stage_242_manifest_hash_rejected(self):
        p, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'binding digest'):
            run(edit_json(p, 5, lambda x: x.update(
                stream_binding_manifest_sha256='0' * 64)))

    def test_wrong_stream_digest_in_receipt_rejected(self):
        p, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            run(edit_json(p, 6, lambda x: x.update(stream_sha256='0' * 64)))

    def test_counter_mismatch_rejected_even_with_matching_hashes(self):
        for key in ('observed_rows', 'first_event_sequence',
                    'last_event_sequence'):
            with self.subTest(key=key):
                p, _ = fixture()
                with self.assertRaisesRegex(ValueError, 'counters mismatch'):
                    run(edit_json(p, 6, lambda x: x.update({key: x[key] + 1})))

    def test_boolean_not_accepted_as_integer_counter(self):
        p, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'counters mismatch'):
            run(edit_json(p, 6, lambda x: x.update(observed_rows=True)))

    def test_unknown_debugger_or_capture_fields_rejected(self):
        for pos, change in (
            (5, lambda x: x['debugger'].update(private_ram_dump='SECRET')),
            (5, lambda x: x['capture_conditions'].update(
                sample_mode='unconstrained')),
            (5, lambda x: x.update(extra_field='SECRET')),
            (6, lambda x: x.update(private_address='SECRET')),
        ):
            with self.subTest(pos=pos, mutation=str(change)):
                p, _ = fixture()
                with self.assertRaises(ValueError):
                    run(edit_json(p, pos, change))

    def test_invalid_nonce_and_version_rejected(self):
        for value in ('0' * 32, 'F' * 32, 'abc', 42):
            with self.subTest(value=value):
                p, _ = fixture()
                with self.assertRaises(ValueError):
                    run(edit_json(p, 5, lambda x: x.update(session_nonce=value)))
        for value in ('', 'foo version', '../secret', False):
            with self.subTest(version=value):
                p, _ = fixture()
                with self.assertRaises(ValueError):
                    run(edit_json(p, 5, lambda x: x['debugger'].update(
                        version=value)))

    def test_duplicate_private_json_keys_rejected(self):
        p, _ = fixture()
        for idx in (5, 6):
            with self.subTest(file_index=idx):
                values = list(p)
                values[idx] = values[idx][:-1] + b',"role":"before"}'
                with self.assertRaisesRegex(ValueError, 'duplicate private JSON field'):
                    run(tuple(values))

    def test_metadata_size_limits_and_missing_file(self):
        self.assertEqual(MAX_PROVENANCE_BYTES, 8192)
        self.assertEqual(MAX_RECEIPT_BYTES, 4096)
        for idx, limit in ((5, MAX_PROVENANCE_BYTES),
                           (6, MAX_RECEIPT_BYTES)):
            p, _ = fixture()
            values = list(p)
            values[idx] = b'x' * (limit + 1)
            with self.assertRaisesRegex(ValueError, 'bounded'):
                run(tuple(values))

    def test_invalid_stage_242_stream_still_rejected(self):
        p, _ = fixture()
        values = list(p)
        values[4] = values[4].replace(b'0x80120000', b'0x80120010', 1)
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            run(tuple(values))

    def test_rehashed_wrong_memory_word_remains_inconsistent(self):
        exe, temporal, binding, rows, streams = payload()
        rows['after'][0]['slot_word_u32'] = '0x80120010'
        streams['after'] = b''.join(_encode(row) + b'\n' for row in rows['after'])
        refresh(binding, streams)
        p = pack(exe, temporal, binding, streams)
        result = run(p)
        self.assertFalse(result['stage_242_stream_claims_consistent'])
        self.assertFalse(result['all_supplied_provenance_claims_consistent'])

    def test_cli_safe_output_for_success_and_corruption(self):
        p, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / ('PRIVATE_TRACE_' + str(i) + '.json')
                     for i in range(1, 9)]
            # The reader is replaced with the synthetic in-memory EXE.
            paths[0].write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'directory': False}]}))
            for path, raw in zip(paths[1:], p[1:]):
                path.write_bytes(raw)

            def invoke():
                stdout = io.StringIO()
                args = ['/private/WildArms.bin', *[str(x) for x in paths]]
                with patch('tools.audit_record_capture_provenance.read_raw_iso_entry',
                           return_value=p[0]), contextlib.redirect_stdout(stdout):
                    code = main(args)
                return code, stdout.getvalue()

            code, result = invoke()
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(result)['all_supplied_provenance_claims_consistent'])
            for secret in (NONCE, '/private/', 'PRIVATE_TRACE_', '0x800d',
                           '0x8012', 'synthetic_debugger', 'a' * 64):
                self.assertNotIn(secret, result)
            paths[-1].write_bytes(b'{SECRET_PRIVATE_ADDRESS')
            code, result = invoke()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(result)['error_code'], 'invalid_private_input')
            self.assertNotIn('SECRET_PRIVATE_ADDRESS', result)


if __name__ == '__main__':
    unittest.main()
