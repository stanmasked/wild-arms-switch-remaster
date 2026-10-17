"""Synthetic-only regression tests for the read-only stage-244 replay gate."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_capture_provenance import (
    fixture as provenance_fixture, pack, NONCE,
)
from tests.test_record_capture_stream_binding import payload, _encode, _sha
from tools.audit_record_capture_replay import (
    analyze, main, _check_ledger, CHALLENGE_SCHEMA, LEDGER_SCHEMA,
    REPORT_SCHEMA, MAX_CHALLENGE_BYTES, MAX_LEDGER_BYTES,
    MAX_LEDGER_ENTRIES,
)

ALT_NONCE = 'abcdef0123456789abcdef0123456789'


def bundle(*, nonce=NONCE, accepted=None):
    exe, temporal, binding, rows, streams = payload()
    p = pack(exe, temporal, binding, streams, nonce=nonce)
    challenge = {
        'schema': CHALLENGE_SCHEMA,
        'session_nonce': nonce,
        'verifier_tag': 'offline_verifier',
        'capture_kind': 'record-slot-samples',
    }
    ledger = {'schema': LEDGER_SCHEMA, 'accepted_sessions': accepted or []}
    return (*p, _encode(challenge), _encode(ledger))


def record(p):
    return {
        'session_nonce': json.loads(p[5])['session_nonce'],
        'provenance_sha256': _sha(p[5]),
        'before_stream_sha256': _sha(p[3]),
        'after_stream_sha256': _sha(p[4]),
    }


def edit_json(p, index, change):
    x = list(p)
    obj = json.loads(x[index])
    change(obj)
    x[index] = _encode(obj)
    return tuple(x)


def old_entry():
    return {
        'session_nonce': 'f' * 32,
        'provenance_sha256': 'a' * 64,
        'before_stream_sha256': 'b' * 64,
        'after_stream_sha256': 'c' * 64,
    }


class ReplayAuditTests(unittest.TestCase):
    def test_new_capture_against_empty_ledger_is_eligible_but_unauthenticated(self):
        p = bundle()
        r = analyze(*p)
        self.assertEqual(r['schema'], REPORT_SCHEMA)
        self.assertTrue(r['eligible_against_supplied_replay_inputs'])
        self.assertTrue(r['verifier_challenge_matches_claimed_session'])
        self.assertEqual(r['accepted_session_ledger_entries_checked'], 0)
        self.assertFalse(r['reused_session_or_stream_detected_in_supplied_ledger'])
        for field in ('challenge_issuance_independently_authenticated',
                      'ledger_integrity_independently_authenticated',
                      'durable_one_time_acceptance_recorded',
                      'replay_prevention_guaranteed',
                      'collector_receipts_cryptographically_authenticated',
                      'original_ps1_execution_verified',
                      'original_game_record_size_verified',
                      'native_switch_game_build_verified',
                      'private_hashes_addresses_or_values_emitted'):
            self.assertFalse(r[field])
        self.assertNotIn(NONCE, str(r))
        self.assertNotIn(_sha(p[3]), str(r))

    def test_different_challenge_refuses_eligible_status(self):
        p = edit_json(bundle(), 8, lambda x: x.update(session_nonce=ALT_NONCE))
        r = analyze(*p)
        self.assertFalse(r['verifier_challenge_matches_claimed_session'])
        self.assertFalse(r['eligible_against_supplied_replay_inputs'])

    def test_exact_prior_capture_rejected(self):
        p = bundle()
        p = edit_json(p, 9, lambda x: x['accepted_sessions'].append(record(p)))
        r = analyze(*p)
        self.assertTrue(r['reused_session_or_stream_detected_in_supplied_ledger'])
        self.assertFalse(r['eligible_against_supplied_replay_inputs'])

    def test_each_individual_replay_key_rejected(self):
        original = bundle()
        current = record(original)
        for key in ('session_nonce', 'provenance_sha256',
                    'before_stream_sha256', 'after_stream_sha256'):
            with self.subTest(key=key):
                old = old_entry()
                old[key] = current[key]
                p = bundle(accepted=[old])
                r = analyze(*p)
                self.assertTrue(r['reused_session_or_stream_detected_in_supplied_ledger'])
                self.assertFalse(r['eligible_against_supplied_replay_inputs'])

    def test_distinct_history_record_is_allowed(self):
        p = bundle(accepted=[old_entry()])
        r = analyze(*p)
        self.assertTrue(r['eligible_against_supplied_replay_inputs'])
        self.assertEqual(r['accepted_session_ledger_entries_checked'], 1)

    def test_two_unique_old_sessions_allowed(self):
        other = {
            'session_nonce': 'e' * 32,
            'provenance_sha256': 'd' * 64,
            'before_stream_sha256': 'e' * 64,
            'after_stream_sha256': 'f' * 64,
        }
        p = bundle(accepted=[old_entry(), other])
        self.assertEqual(analyze(*p)['accepted_session_ledger_entries_checked'], 2)

    def test_reusing_single_role_stream_with_new_nonce_rejected(self):
        exe, temporal, binding, rows, streams = payload()
        old = record(pack(exe, temporal, binding, streams, nonce=ALT_NONCE))
        p = bundle(accepted=[old])
        r = analyze(*p)
        self.assertTrue(r['reused_session_or_stream_detected_in_supplied_ledger'])
        self.assertFalse(r['eligible_against_supplied_replay_inputs'])

    def test_duplicate_accepted_nonce_rejected_as_bad_ledger(self):
        first, second = old_entry(), old_entry()
        second.update(provenance_sha256='d'*64,
                      before_stream_sha256='e'*64,
                      after_stream_sha256='f'*64)
        with self.assertRaisesRegex(ValueError, 'reused'):
            analyze(*bundle(accepted=[first, second]))

    def test_duplicate_accepted_digest_rejected_even_with_unique_nonce(self):
        for field in ('provenance_sha256', 'before_stream_sha256',
                      'after_stream_sha256'):
            with self.subTest(field=field):
                first, second = old_entry(), old_entry()
                second.update(session_nonce='e'*32,
                              provenance_sha256='d'*64,
                              before_stream_sha256='e'*64,
                              after_stream_sha256='f'*64)
                second[field] = first[field]
                with self.assertRaisesRegex(ValueError, 'reused'):
                    analyze(*bundle(accepted=[first, second]))

    def test_same_before_and_after_sha_in_old_entry_refused(self):
        old = old_entry()
        old['after_stream_sha256'] = old['before_stream_sha256']
        with self.assertRaisesRegex(ValueError, 'reused'):
            analyze(*bundle(accepted=[old]))

    def test_ledger_invalid_nonce_digest_and_boolean_types(self):
        for field, value in (
            ('session_nonce', '0' * 32),
            ('session_nonce', True),
            ('provenance_sha256', 'a' * 63),
            ('before_stream_sha256', 'A' * 64),
            ('after_stream_sha256', False),
        ):
            with self.subTest(field=field, value=value):
                old = old_entry()
                old[field] = value
                with self.assertRaises(ValueError):
                    analyze(*bundle(accepted=[old]))

    def test_strict_challenge_schema(self):
        for change in (
            lambda x: x.update(capture_kind='another-kind'),
            lambda x: x.update(verifier_tag='../not_tag'),
            lambda x: x.update(schema='wrong'),
            lambda x: x.update(extra='SECRET'),
            lambda x: x.update(session_nonce='A' * 32),
            lambda x: x.update(session_nonce=True),
        ):
            with self.subTest(change=str(change)):
                with self.assertRaises(ValueError):
                    analyze(*edit_json(bundle(), 8, change))

    def test_strict_ledger_schema_and_entry_fields(self):
        for change in (
            lambda x: x.update(schema='wrong'),
            lambda x: x.update(extra='SECRET'),
            lambda x: x.update(accepted_sessions={}),
            lambda x: x.update(accepted_sessions=[dict(old_entry(), extra='SECRET')]),
        ):
            with self.subTest(change=str(change)):
                with self.assertRaises(ValueError):
                    analyze(*edit_json(bundle(), 9, change))

    def test_duplicate_json_key_in_challenge_or_ledger_rejected(self):
        for idx, append in ((8, b',"schema":"duplicate"}'),
                            (9, b',"schema":"duplicate"}')):
            with self.subTest(idx=idx):
                p = list(bundle())
                p[idx] = p[idx][:-1] + append
                with self.assertRaisesRegex(ValueError, 'duplicate private JSON field'):
                    analyze(*p)

    def test_challenge_and_ledger_size_limits(self):
        self.assertEqual(MAX_CHALLENGE_BYTES, 4096)
        self.assertEqual(MAX_LEDGER_BYTES, 256 * 1024)
        self.assertEqual(MAX_LEDGER_ENTRIES, 512)
        for idx, size in ((8, MAX_CHALLENGE_BYTES), (9, MAX_LEDGER_BYTES)):
            p = list(bundle())
            p[idx] = b'x' * (size + 1)
            with self.assertRaisesRegex(ValueError, 'bounded'):
                analyze(*p)
        data = _encode({'schema': LEDGER_SCHEMA,
                        'accepted_sessions': [old_entry()] * 513})
        with self.assertRaises(ValueError):
            _check_ledger(data)

    def test_stage_243_bad_data_fails_before_replay(self):
        p = list(bundle())
        p[4] = p[4].replace(b'0x80120000', b'0x80120010', 1)
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            analyze(*p)

    def test_inconsistent_stage_243_never_eligible(self):
        exe, temporal, binding, rows, streams = payload()
        rows['after'][0]['slot_word_u32'] = '0x80120010'
        streams['after'] = b''.join(_encode(r) + b'\n' for r in rows['after'])
        binding['streams'][1]['sha256'] = _sha(streams['after'])
        p = pack(exe, temporal, binding, streams)
        challenge = bundle()[8]
        ledger = bundle()[9]
        r = analyze(*p, challenge, ledger)
        self.assertFalse(r['stage_243_provenance_claims_consistent'])
        self.assertFalse(r['eligible_against_supplied_replay_inputs'])

    def test_cli_outputs_are_private_safe(self):
        p = bundle()
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / ('PRIVATE_EVIDENCE_' + str(i) + '.json')
                     for i in range(10)]
            paths[0].write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'directory': False}]}))
            for path, raw in zip(paths[1:], p[1:]):
                path.write_bytes(raw)

            def invoke():
                out = io.StringIO()
                with patch('tools.audit_record_capture_replay.read_raw_iso_entry',
                           return_value=p[0]), contextlib.redirect_stdout(out):
                    code = main(['/private/WildArms.bin', *map(str, paths)])
                return code, out.getvalue()

            code, output = invoke()
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)['eligible_against_supplied_replay_inputs'])
            for private in (NONCE, '/private/', 'PRIVATE_EVIDENCE_',
                            '0x800d', '0x8012', _sha(p[3])):
                self.assertNotIn(private, output)

            paths[-1].write_bytes(_encode({'schema': LEDGER_SCHEMA,
                                          'accepted_sessions': [record(p)]}))
            code, output = invoke()
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)['eligible_against_supplied_replay_inputs'])

            paths[-1].write_bytes(b'{PRIVATE_ADDR_0x800d')
            code, output = invoke()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_ADDR', output)
            self.assertNotIn('Traceback', output)


if __name__ == '__main__':
    unittest.main()
