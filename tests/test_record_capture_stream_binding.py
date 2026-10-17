"""Synthetic-only PS1 private capture stream digest and binding tests."""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_temporal_slot_snapshots import temporal_fixture
from tools.audit_record_capture_stream_binding import (
    SCHEMA, REPORT_SCHEMA, MAX_STREAM_BYTES, _parse, analyze, main,
)

SESSION = 'synthetic-run-01'
COLLECTORS = {'before': 'memory_watch', 'after': 'memory_snapshot'}


def _encode(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def payload(*, sites=(0, 1)):
    exe, claim = temporal_fixture(sites=sites)
    claim_raw = _encode(claim)
    rows = {'before': [], 'after': []}
    for w in claim['read_windows']:
        for role in ('before', 'after'):
            data = {
                'session_tag': SESSION,
                'site': w['site'],
                'record_index': w['record_index'],
                'execution_tag': w['execution_tag'],
                **w[role],
            }
            rows[role].append(data)
    streams = {
        role: b''.join(_encode(row) + b'\n' for row in rows[role])
        for role in ('before', 'after')
    }
    manifest = {
        'schema': SCHEMA, 'session_tag': SESSION,
        'exe_sha256': _sha(exe),
        'temporal_claim_sha256': _sha(claim_raw),
        'streams': [
            {'role': role, 'collector_tag': COLLECTORS[role],
             'sha256': _sha(streams[role])}
            for role in ('before', 'after')
        ],
    }
    return exe, claim_raw, manifest, rows, streams


def refresh(manifest, streams):
    for stream in manifest['streams']:
        stream['sha256'] = _sha(streams[stream['role']])


def run_fixture(exe, claim_raw, manifest, streams):
    return analyze(exe, claim_raw, _encode(manifest),
                   streams['before'], streams['after'])


class CaptureStreamBindingTests(unittest.TestCase):
    def test_six_pairs_are_bound_to_exact_exe_claim_and_stream_digests(self):
        exe, claim, manifest, rows, streams = payload()
        result = run_fixture(exe, claim, manifest, streams)
        self.assertEqual(result['schema'], REPORT_SCHEMA)
        self.assertEqual(result['distinct_claimed_capture_streams'], 2)
        self.assertEqual(result['claimed_stream_rows_checked'], 12)
        self.assertEqual(result['stream_pairs_matching_temporal_claim'], 6)
        self.assertTrue(result['exe_image_digest_matched'])
        self.assertTrue(result['temporal_claim_digest_matched'])
        self.assertTrue(result['prior_temporal_slot_claims_consistent'])
        self.assertTrue(result['all_supplied_stream_claims_consistent'])
        for name in ('collection_origin_independently_authenticated',
                     'raw_memory_observation_authenticated',
                     'original_ps1_execution_verified',
                     'original_game_record_size_verified',
                     'native_switch_game_build_verified',
                     'private_hashes_addresses_or_values_emitted'):
            self.assertFalse(result[name])
        self.assertNotIn('0x800d', str(result))
        self.assertNotIn('0x8012', str(result))

    def test_three_sites_nine_windows_are_bound(self):
        exe, claim, manifest, rows, streams = payload(sites=(0, 1, 2))
        r = run_fixture(exe, claim, manifest, streams)
        self.assertTrue(r['all_supplied_stream_claims_consistent'])
        self.assertEqual(r['claimed_window_pairs_checked'], 9)
        self.assertEqual(r['claimed_stream_rows_checked'], 18)

    def test_changed_stream_byte_without_manifest_update_is_rejected(self):
        exe, claim, manifest, rows, streams = payload()
        streams['after'] = streams['after'].replace(b'0x80120000', b'0x80120010', 1)
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            run_fixture(exe, claim, manifest, streams)

    def test_rehashed_changed_memory_word_does_not_match_temporal_claim(self):
        exe, claim, manifest, rows, streams = payload()
        rows['after'][0]['slot_word_u32'] = '0x80120010'
        streams['after'] = b''.join(_encode(r) + b'\n' for r in rows['after'])
        refresh(manifest, streams)
        result = run_fixture(exe, claim, manifest, streams)
        self.assertEqual(result['stream_pairs_matching_temporal_claim'], 5)
        self.assertFalse(result['all_supplied_stream_claims_consistent'])
        self.assertNotIn('0x80120010', str(result))

    def test_exe_digest_drift_is_rejected(self):
        exe, claim, manifest, rows, streams = payload()
        changed = bytearray(exe)
        changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            run_fixture(bytes(changed), claim, manifest, streams)

    def test_temporal_claim_digest_drift_is_rejected(self):
        exe, claim, manifest, rows, streams = payload()
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            run_fixture(exe, claim + b' ', manifest, streams)

    def test_forged_matching_hashes_never_authenticate_capture_origin(self):
        exe, claim, manifest, rows, streams = payload()
        manifest['session_tag'] = SESSION
        result = run_fixture(exe, claim, manifest, streams)
        self.assertTrue(result['all_supplied_stream_claims_consistent'])
        self.assertFalse(result['collection_origin_independently_authenticated'])
        self.assertFalse(result['raw_memory_observation_authenticated'])

    def test_swapped_before_after_files_are_rejected(self):
        exe, claim, manifest, rows, streams = payload()
        streams['before'], streams['after'] = streams['after'], streams['before']
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            run_fixture(exe, claim, manifest, streams)

    def test_recomputed_manifest_does_not_hide_wrong_capture_session(self):
        exe, claim, manifest, rows, streams = payload()
        rows['before'][0]['session_tag'] = 'other-run'
        streams['before'] = b''.join(_encode(r) + b'\n' for r in rows['before'])
        refresh(manifest, streams)
        with self.assertRaisesRegex(ValueError, 'row metadata'):
            run_fixture(exe, claim, manifest, streams)

    def test_wrong_stream_collector_even_with_recomputed_hash_is_rejected(self):
        exe, claim, manifest, rows, streams = payload()
        rows['before'][0]['collector_tag'] = 'memory_snapshot'
        streams['before'] = b''.join(_encode(r) + b'\n' for r in rows['before'])
        refresh(manifest, streams)
        with self.assertRaisesRegex(ValueError, 'row metadata'):
            run_fixture(exe, claim, manifest, streams)

    def test_changed_execution_tag_does_not_match_private_temporal_window(self):
        exe, claim, manifest, rows, streams = payload()
        rows['before'][0]['execution_tag'] = 'different_event'
        streams['before'] = b''.join(_encode(r) + b'\n' for r in rows['before'])
        refresh(manifest, streams)
        result = run_fixture(exe, claim, manifest, streams)
        self.assertEqual(result['stream_pairs_matching_temporal_claim'], 5)
        self.assertFalse(result['all_supplied_stream_claims_consistent'])

    def test_out_of_order_stream_events_are_refused(self):
        exe, claim, manifest, rows, streams = payload()
        rows['before'][0], rows['before'][1] = rows['before'][1], rows['before'][0]
        streams['before'] = b''.join(_encode(r) + b'\n' for r in rows['before'])
        refresh(manifest, streams)
        with self.assertRaisesRegex(ValueError, 'unordered'):
            run_fixture(exe, claim, manifest, streams)

    def test_duplicate_index_and_missing_or_extra_entries_refused(self):
        for mutation in ('duplicate', 'missing', 'extra'):
            with self.subTest(mutation=mutation):
                exe, claim, manifest, rows, streams = payload()
                if mutation == 'duplicate':
                    rows['before'][1]['record_index'] = rows['before'][0]['record_index']
                    rows['before'][1]['site'] = rows['before'][0]['site']
                elif mutation == 'missing':
                    rows['before'].pop()
                else:
                    rows['before'].append(copy.deepcopy(rows['before'][-1]))
                streams['before'] = b''.join(_encode(r) + b'\n' for r in rows['before'])
                refresh(manifest, streams)
                with self.assertRaises(ValueError):
                    run_fixture(exe, claim, manifest, streams)

    def test_malformed_manifest_roles_and_fake_same_collector_are_refused(self):
        for mutation in ('missing', 'duplicate', 'collector', 'digest-case'):
            with self.subTest(mutation=mutation):
                exe, claim, manifest, rows, streams = payload()
                if mutation == 'missing':
                    manifest['streams'].pop()
                elif mutation == 'duplicate':
                    manifest['streams'][1]['role'] = 'before'
                elif mutation == 'collector':
                    manifest['streams'][1]['collector_tag'] = 'memory_watch'
                else:
                    manifest['exe_sha256'] = manifest['exe_sha256'].upper()
                with self.assertRaises(ValueError):
                    run_fixture(exe, claim, manifest, streams)

    def test_duplicate_json_fields_in_manifest_and_row_are_rejected(self):
        exe, claim, manifest, rows, streams = payload()
        with self.assertRaisesRegex(ValueError, 'duplicate private JSON field'):
            analyze(exe, claim, b'{"schema":"a","schema":"b"}',
                    streams['before'], streams['after'])
        duplicate = (_encode(rows['before'][0])[:-1] +
                     b',"site":"site_9"}\n')
        streams['before'] = duplicate + streams['before'].split(b'\n', 1)[1]
        refresh(manifest, streams)
        with self.assertRaisesRegex(ValueError, 'duplicate private JSON field'):
            run_fixture(exe, claim, manifest, streams)

    def test_private_unexpected_fields_and_bad_types_are_rejected(self):
        for mutation in ('extra', 'boolean-index', 'numeric-address'):
            with self.subTest(mutation=mutation):
                exe, claim, manifest, rows, streams = payload()
                if mutation == 'extra':
                    rows['before'][0]['PRIVATE_GPR_DUMP'] = 'SECRET'
                elif mutation == 'boolean-index':
                    rows['before'][0]['record_index'] = True
                else:
                    rows['before'][0]['at_pc_u32'] = 0x8006d27c
                streams['before'] = b''.join(_encode(r) + b'\n' for r in rows['before'])
                refresh(manifest, streams)
                if mutation == 'numeric-address':
                    result = run_fixture(exe, claim, manifest, streams)
                    self.assertFalse(result['all_supplied_stream_claims_consistent'])
                else:
                    with self.assertRaises(ValueError):
                        run_fixture(exe, claim, manifest, streams)

    def test_missing_terminal_newline_and_empty_lines_are_rejected(self):
        for mutation in ('no-terminal', 'empty-entry'):
            with self.subTest(mutation=mutation):
                exe, claim, manifest, rows, streams = payload()
                streams['after'] = (
                    streams['after'].rstrip(b'\n') if mutation == 'no-terminal'
                    else b'\n' + streams['after'])
                refresh(manifest, streams)
                with self.assertRaises(ValueError):
                    run_fixture(exe, claim, manifest, streams)

    def test_private_cli_success_mismatch_invalid_are_sanitized(self):
        exe, claim, manifest, rows, streams = payload()
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            inventory = root / 'disc-inventory.json'
            inventory.write_text(json.dumps({'entries': [{
                'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                'size': len(exe), 'directory': False}]}))
            private_claim = root / 'PRIVATE_TEMPORAL_0x800d.json'
            private_manifest = root / 'PRIVATE_MANIFEST.json'
            before = root / 'PRIVATE_BEFORE.jsonl'
            after = root / 'PRIVATE_AFTER.jsonl'
            private_claim.write_bytes(claim)
            def call():
                private_manifest.write_bytes(_encode(manifest))
                before.write_bytes(streams['before'])
                after.write_bytes(streams['after'])
                output = io.StringIO()
                with patch('tools.audit_record_capture_stream_binding.read_raw_iso_entry',
                           return_value=exe):
                    with contextlib.redirect_stdout(output):
                        code = main(['/private/WildArms.bin', str(inventory),
                                     str(private_claim), str(private_manifest),
                                     str(before), str(after)])
                return code, output.getvalue()
            code, output = call()
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)['all_supplied_stream_claims_consistent'])
            for token in ('0x800d', '0x8012', 'PRIVATE_', '/private/'):
                self.assertNotIn(token, output)

            rows['after'][0]['slot_word_u32'] = '0x80120010'
            streams['after'] = b''.join(_encode(r) + b'\n' for r in rows['after'])
            refresh(manifest, streams)
            code, output = call()
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)['all_supplied_stream_claims_consistent'])
            self.assertNotIn('0x80120010', output)

            private_claim.write_bytes(b'{PRIVATE_RAM_0x800d2c3c')
            code, output = call()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_RAM', output)
            self.assertNotIn('Traceback', output)

    def test_absent_private_input_and_file_size_limit_do_not_leak(self):
        self.assertEqual(MAX_STREAM_BYTES, 128 * 1024)
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(['/private/WildArms.bin',
                             str(Path(tmp)/'PRIVATE_MISSING_INVENTORY.json'),
                             str(Path(tmp)/'claim.json'),
                             str(Path(tmp)/'manifest.json'),
                             str(Path(tmp)/'before.jsonl'),
                             str(Path(tmp)/'after.jsonl')])
            self.assertEqual(code, 2)
            self.assertNotIn('PRIVATE_MISSING', out.getvalue())
            self.assertFalse(json.loads(out.getvalue())[
                'private_hashes_addresses_or_values_emitted'])


if __name__ == '__main__':
    unittest.main()
