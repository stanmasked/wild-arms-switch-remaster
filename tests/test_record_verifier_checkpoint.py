"""Synthetic-only stage-246 verifier state rollback/continuity regression tests."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import fixture, NONCE_A, NONCE_B, FIXED_NOW
from tools.audit_record_atomic_verifier import issue, accept
from tools.audit_record_verifier_checkpoint import (
    SCHEMA, REPORT_SCHEMA, MAX_CHECKPOINT_BYTES, MAX_ROWS,
    _read_database, _validate_checkpoint, check, save_checkpoint, main,
)


class VerifierCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.db_dir = self.root / 'verifier'
        self.anchor_dir = self.root / 'separately-retained'
        self.db_dir.mkdir(mode=0o700)
        self.anchor_dir.mkdir(mode=0o700)
        self.db = self.db_dir / 'sessions.sqlite'
        self.anchor = self.anchor_dir / 'checkpoint.json'

    def issue_nonce(self, nonce=NONCE_A):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=nonce):
            issue(self.db, now=FIXED_NOW)

    def accept_nonce(self, nonce=NONCE_A):
        return accept(self.db, *fixture(nonce), now=FIXED_NOW + 1)

    def checkpoint(self, name='checkpoint.json'):
        target = self.anchor_dir / name
        report = save_checkpoint(self.db, target)
        self.assertTrue(report['checkpoint_file_created'])
        self.assertFalse(report['checkpoint_independently_authenticated'])
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        return target.read_bytes()

    def test_empty_issued_state_snapshot_and_validation(self):
        self.issue_nonce()
        data = self.checkpoint()
        value = json.loads(data)
        self.assertEqual(value['schema'], SCHEMA)
        self.assertEqual(len(value['issued_commitments']), 1)
        self.assertEqual(len(value['accepted_commitments']), 0)
        self.assertNotIn(NONCE_A, data.decode())
        report = check(self.db, data)
        self.assertTrue(report['continuous_relative_to_supplied_checkpoint'])
        self.assertFalse(report['checkpoint_independently_authenticated'])
        self.assertFalse(report['database_rollback_globally_excluded'])
        self.assertFalse(report['original_ps1_execution_verified'])

    def test_anchor_keeps_valid_history_after_later_acceptance(self):
        self.issue_nonce()
        data = self.checkpoint()
        self.assertTrue(self.accept_nonce())
        report = check(self.db, data)
        self.assertTrue(report['all_prior_issued_sessions_preserved'])
        self.assertTrue(report['continuous_relative_to_supplied_checkpoint'])
        self.assertEqual(report['prior_accepted_sessions_checked'], 0)

    def test_anchor_with_accepted_history_allows_later_new_issuance(self):
        self.issue_nonce()
        self.assertTrue(self.accept_nonce())
        data = self.checkpoint()
        self.issue_nonce(NONCE_B)
        r = check(self.db, data)
        self.assertTrue(r['continuous_relative_to_supplied_checkpoint'])
        self.assertEqual(r['prior_accepted_sessions_checked'], 1)

    def test_restoring_pre_acceptance_database_detected(self):
        self.issue_nonce()
        backup = self.db_dir / 'older.sqlite'
        shutil.copyfile(self.db, backup)
        self.assertTrue(self.accept_nonce())
        data = self.checkpoint()
        shutil.copyfile(backup, self.db)
        r = check(self.db, data)
        self.assertFalse(r['all_prior_accepted_sessions_preserved'])
        self.assertFalse(r['continuous_relative_to_supplied_checkpoint'])

    def test_restoring_pre_issuance_database_detected(self):
        self.issue_nonce()
        backup = self.db_dir / 'older.sqlite'
        shutil.copyfile(self.db, backup)
        self.issue_nonce(NONCE_B)
        data = self.checkpoint()
        shutil.copyfile(backup, self.db)
        r = check(self.db, data)
        self.assertFalse(r['all_prior_issued_sessions_preserved'])
        self.assertFalse(r['continuous_relative_to_supplied_checkpoint'])

    def test_previous_accepted_record_modification_detected(self):
        self.issue_nonce()
        self.assertTrue(self.accept_nonce())
        data = self.checkpoint()
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE accepted SET provenance_sha256=?',
                        ('d' * 64,))
        self.assertFalse(check(self.db, data)[
            'all_prior_accepted_sessions_preserved'])

    def test_previous_issue_expiry_modification_detected(self):
        self.issue_nonce()
        data = self.checkpoint()
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE challenges SET expires_at=expires_at+1')
        self.assertFalse(check(self.db, data)['all_prior_issued_sessions_preserved'])

    def test_consumed_without_accepted_row_refused(self):
        self.issue_nonce()
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE challenges SET consumed=1')
        with self.assertRaisesRegex(ValueError, 'without acceptance'):
            _read_database(self.db)

    def test_missing_stream_evidence_refused(self):
        self.issue_nonce()
        self.assertTrue(self.accept_nonce())
        with sqlite3.connect(self.db) as con:
            con.execute('DELETE FROM accepted_streams WHERE rowid='
                        '(SELECT min(rowid) FROM accepted_streams)')
        with self.assertRaisesRegex(ValueError, 'missing accepted stream'):
            _read_database(self.db)

    def test_foreign_key_violation_refused(self):
        self.issue_nonce()
        with sqlite3.connect(self.db) as con:
            con.execute('INSERT INTO accepted_streams VALUES (?, ?)',
                        ('d' * 64, NONCE_B))
        with self.assertRaisesRegex(ValueError, 'foreign keys'):
            _read_database(self.db)

    def test_checkpoint_double_write_is_refused_not_overwritten(self):
        self.issue_nonce()
        baseline = self.checkpoint()
        with self.assertRaises(FileExistsError):
            save_checkpoint(self.db, self.anchor)
        self.assertEqual(self.anchor.read_bytes(), baseline)

    def test_symlink_and_world_readable_database_refused(self):
        self.issue_nonce()
        link = self.db_dir / 'linked.sqlite'
        link.symlink_to(self.db)
        with self.assertRaises(ValueError):
            _read_database(link)
        os.chmod(self.db, 0o644)
        with self.assertRaises(ValueError):
            _read_database(self.db)
        os.chmod(self.db, 0o600)

    def test_public_destination_directory_refused(self):
        self.issue_nonce()
        public = self.root / 'public-dir'
        public.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, 'not private'):
            save_checkpoint(self.db, public / 'unsafe.json')

    def test_invalid_checkpoints_rejected_without_output_leak(self):
        self.issue_nonce()
        baseline = self.checkpoint()
        invalid = [
            b'',
            b'{ "schema":"x", "schema":"x" }',
            baseline[:-1] + b' extra',
            json.dumps({'schema': SCHEMA, 'issued_commitments': {},
                        'accepted_commitments': []}).encode(),
            json.dumps({'schema': SCHEMA, 'issued_commitments': ['F'*64],
                        'accepted_commitments': []}).encode(),
            json.dumps({'schema': SCHEMA, 'issued_commitments': ['a'*64] * 2,
                        'accepted_commitments': []}).encode(),
            b'x' * (MAX_CHECKPOINT_BYTES + 1),
        ]
        for item in invalid:
            with self.subTest(sample=item[:20]):
                with self.assertRaises((ValueError, UnicodeError)):
                    check(self.db, item)

    def test_reordered_valid_digest_list_refused(self):
        self.issue_nonce()
        self.issue_nonce(NONCE_B)
        original = json.loads(self.checkpoint())
        original['issued_commitments'].reverse()
        with self.assertRaisesRegex(ValueError, 'unsorted'):
            _validate_checkpoint(json.dumps(original).encode())

    def test_history_limit_guard(self):
        self.assertEqual(MAX_ROWS, 4096)
        oversized = {
            'schema': SCHEMA, 'issued_commitments': ['a'*64] * (MAX_ROWS + 1),
            'accepted_commitments': [],
        }
        with self.assertRaises(ValueError):
            _validate_checkpoint(json.dumps(oversized).encode())

    def test_different_database_with_same_counts_fails_continuity(self):
        self.issue_nonce()
        original = self.checkpoint()
        other_dir = self.root / 'other-verifier'
        other_dir.mkdir(mode=0o700)
        other = other_dir / 'other.sqlite'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            issue(other, now=FIXED_NOW)
        self.assertFalse(check(other, original)['continuous_relative_to_supplied_checkpoint'])

    def test_cli_snapshot_verify_and_private_safe_failure(self):
        self.issue_nonce()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['snapshot', str(self.db), str(self.anchor)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout.getvalue())['checkpoint_file_created'])
        self.assertNotIn(NONCE_A, stdout.getvalue())
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['verify', str(self.db), str(self.anchor)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout.getvalue())[
            'continuous_relative_to_supplied_checkpoint'])
        self.assertNotIn(self.db.name, stdout.getvalue())
        self.assertNotIn(NONCE_A, stdout.getvalue())
        self.issue_nonce(NONCE_B)
        self.assertFalse(check(self.db, self.anchor.read_bytes())[
            'database_rollback_globally_excluded'])
        with sqlite3.connect(self.db) as con:
            con.execute('DELETE FROM challenges WHERE nonce=?', (NONCE_A,))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['verify', str(self.db), str(self.anchor)])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(stdout.getvalue())[
            'continuous_relative_to_supplied_checkpoint'])
        self.assertNotIn(NONCE_A, stdout.getvalue())

    def test_cli_reports_generic_error_for_corrupt_checkpoint(self):
        self.issue_nonce()
        self.anchor.write_bytes(b'{PRIVATE_SECRET_NONCE')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['verify', str(self.db), str(self.anchor)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['error_code'],
                         'invalid_private_input')
        self.assertNotIn('PRIVATE_SECRET_NONCE', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
