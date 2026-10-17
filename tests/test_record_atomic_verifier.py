"""Stage-245 synthetic-only tests for verifier-owned SQLite one-use capture."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_capture_provenance import pack
from tests.test_record_capture_stream_binding import payload, _encode, _sha
from tools.audit_record_atomic_verifier import (
    REPORT_SCHEMA, ISSUE_SCHEMA, issue, accept, main, _result,
)

FIXED_NOW = 1760000000
NONCE_A = '0123456789abcdeffedcba9876543210'
NONCE_B = 'abcdef0123456789abcdef0123456789'
NONCE_C = 'fedcba9876543210fedcba9876543210'


def fixture(nonce):
    exe, temporal, manifest, rows, streams = payload()
    return pack(exe, temporal, manifest, streams, nonce=nonce)


class AtomicVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'private-verifier.sqlite'

    def challenge(self, nonce=NONCE_A, ttl=300, now=FIXED_NOW):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=nonce):
            self.assertEqual(issue(self.db, ttl_seconds=ttl, now=now), nonce)

    def test_issue_and_accept_once_survives_restart(self):
        self.challenge()
        evidence = fixture(NONCE_A)
        self.assertTrue(accept(self.db, *evidence, now=FIXED_NOW + 1))
        self.assertFalse(accept(self.db, *evidence, now=FIXED_NOW + 2))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM accepted').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM accepted_streams').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT consumed FROM challenges').fetchone()[0], 1)
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(NONCE_A, str(_result(True)))
        self.assertFalse(_result(True)['original_ps1_execution_verified'])
        self.assertFalse(_result(True)['external_database_integrity_attested'])

    def test_missing_issued_nonce_fails_without_registering_evidence(self):
        self.challenge(NONCE_B)
        self.assertFalse(accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 1))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM accepted').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT consumed FROM challenges').fetchone()[0], 0)

    def test_expired_challenge_not_consumed(self):
        self.challenge(ttl=30)
        self.assertFalse(accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 30))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT consumed FROM challenges').fetchone()[0], 0)
        self.assertTrue(accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 29))

    def test_stage_243_mismatch_does_not_spend_challenge(self):
        self.challenge()
        evidence = list(fixture(NONCE_A))
        evidence[4] = evidence[4].replace(b'0x80120000', b'0x80120010', 1)
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            accept(self.db, *evidence, now=FIXED_NOW + 1)
        self.assertTrue(accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 2))

    def test_coherent_but_conflicting_snapshot_does_not_spend_nonce(self):
        self.challenge()
        exe, temporal, binding, rows, streams = payload()
        rows['after'][0]['slot_word_u32'] = '0x80120010'
        streams['after'] = b''.join(_encode(r) + b'\n' for r in rows['after'])
        binding['streams'][1]['sha256'] = _sha(streams['after'])
        bad = pack(exe, temporal, binding, streams, nonce=NONCE_A)
        self.assertFalse(accept(self.db, *bad, now=FIXED_NOW + 1))
        self.assertTrue(accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 2))

    def test_new_nonce_with_old_raw_streams_is_rejected_atomically(self):
        self.challenge()
        self.challenge(NONCE_B)
        self.assertTrue(accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 1))
        # A second claim may have its own valid receipts and provenance
        # but reused before/after raw evidence must not be accepted.
        self.assertFalse(accept(self.db, *fixture(NONCE_B), now=FIXED_NOW + 2))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT consumed FROM challenges WHERE nonce=?',
                                       (NONCE_B,)).fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM accepted').fetchone()[0], 1)

    def test_unexpired_challenge_only_accepts_matching_nonce(self):
        self.challenge(NONCE_B)
        self.assertFalse(accept(self.db, *fixture(NONCE_C), now=FIXED_NOW + 1))
        self.assertTrue(accept(self.db, *fixture(NONCE_B), now=FIXED_NOW + 2))

    def test_concurrent_accept_same_capture_only_one_wins(self):
        self.challenge()
        evidence = fixture(NONCE_A)
        def contender(_):
            return accept(self.db, *evidence, now=FIXED_NOW + 2)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(contender, range(6)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 5)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM accepted').fetchone()[0], 1)

    def test_issued_nonce_not_derived_from_user_evidence(self):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   side_effect=[NONCE_A, NONCE_B]) as random_nonce:
            self.assertEqual(issue(self.db, now=FIXED_NOW), NONCE_A)
            self.assertEqual(issue(self.db, now=FIXED_NOW), NONCE_B)
            self.assertEqual(random_nonce.call_count, 2)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM challenges').fetchone()[0], 2)

    def test_invalid_ttl_or_nonce_collision_rolls_back(self):
        for invalid in (True, 0, -1, 29, 3601, 1.5):
            with self.subTest(ttl=invalid):
                with self.assertRaises(ValueError):
                    issue(self.db, ttl_seconds=invalid, now=FIXED_NOW)
        self.challenge()
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            with self.assertRaises(sqlite3.IntegrityError):
                issue(self.db, now=FIXED_NOW)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM challenges').fetchone()[0], 1)

    def test_private_path_and_symlink_checks(self):
        self.challenge()
        symlink = Path(self.tmp.name) / 'forbidden-symlink.sqlite'
        symlink.symlink_to(self.db)
        with self.assertRaises(ValueError):
            issue(symlink, now=FIXED_NOW)
        os.chmod(self.db, 0o644)
        with self.assertRaises(ValueError):
            issue(self.db, now=FIXED_NOW)
        os.chmod(self.db, 0o600)
        os.chmod(self.tmp.name, 0o755)
        with self.assertRaises(ValueError):
            issue(self.db, now=FIXED_NOW)
        os.chmod(self.tmp.name, 0o700)

    def test_database_not_implicitly_created_during_accept(self):
        with self.assertRaises(FileNotFoundError):
            accept(self.db, *fixture(NONCE_A), now=FIXED_NOW + 1)
        self.assertFalse(self.db.exists())

    def test_cli_issue_accept_and_redacted_rejection(self):
        # CLI issue deliberately exposes its one-use nonce to the private
        # recorder. CLI accept must never print that nonce or raw evidence.
        issue_output = io.StringIO()
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A), patch(
                   'tools.audit_record_atomic_verifier.time.time',
                   return_value=FIXED_NOW), contextlib.redirect_stdout(issue_output):
            code = main(['issue', str(self.db), '--ttl-seconds', '300'])
        self.assertEqual(code, 0)
        issued = json.loads(issue_output.getvalue())
        self.assertEqual(issued['schema'], ISSUE_SCHEMA)
        self.assertEqual(issued['session_nonce'], NONCE_A)

        evidence = fixture(NONCE_A)
        with tempfile.TemporaryDirectory() as artifacts:
            inventory = Path(artifacts) / 'inventory.json'
            inventory.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'directory': False}]}))
            paths = [Path(artifacts) / ('PRIVATE_RECORD_' + str(i) + '.json')
                     for i in range(7)]
            for p, raw in zip(paths, evidence[1:]):
                p.write_bytes(raw)
            argv = ['accept', str(self.db), '/private/WildArms.bin',
                    str(inventory), *[str(x) for x in paths]]
            def invoke():
                stdout = io.StringIO()
                with patch('tools.audit_record_atomic_verifier.read_raw_iso_entry',
                           return_value=evidence[0]), patch(
                           'tools.audit_record_atomic_verifier.time.time',
                           return_value=FIXED_NOW + 1), contextlib.redirect_stdout(stdout):
                    code = main(argv)
                return code, stdout.getvalue()
            status, printed = invoke()
            self.assertEqual(status, 0)
            self.assertTrue(json.loads(printed)['accepted_once'])
            for private in (NONCE_A, '/private/', 'PRIVATE_RECORD_', '0x800d',
                            '0x8012', _sha(evidence[3])):
                self.assertNotIn(private, printed)
            status, printed = invoke()
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(printed)['accepted_once'])
            paths[-1].write_bytes(b'{PRIVATE_PC_0x800d')
            status, printed = invoke()
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(printed)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_PC_', printed)


if __name__ == '__main__':
    unittest.main()
