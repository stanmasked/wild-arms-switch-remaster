"""Synthetic-only stage-247 tests: fail-closed, locked continuity admission."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import (
    fixture, NONCE_A, NONCE_B, FIXED_NOW,
)
from tools.audit_record_atomic_verifier import issue as legacy_issue
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_guarded_admission import (
    ContinuityRegression, issue_guarded, accept_guarded, main, _report,
)

NONCE_C = 'fedcba9876543210fedcba9876543210'


class GuardedAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.verifier = root / 'verifier'
        self.anchor_dir = root / 'external-checkpoint'
        self.verifier.mkdir(mode=0o700)
        self.anchor_dir.mkdir(mode=0o700)
        self.db = self.verifier / 'verifier.sqlite'
        self.anchor = self.anchor_dir / 'checkpoint.json'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            legacy_issue(self.db, now=FIXED_NOW)
        self.refresh_checkpoint()

    def refresh_checkpoint(self, name=None):
        path = self.anchor if name is None else self.anchor_dir / name
        save_checkpoint(self.db, path)
        return path

    def state(self):
        with sqlite3.connect(self.db) as c:
            return (c.execute('SELECT COUNT(*) FROM challenges').fetchone()[0],
                    c.execute('SELECT COUNT(*) FROM accepted').fetchone()[0],
                    c.execute('SELECT COUNT(*) FROM accepted_streams').fetchone()[0])

    def new_issue(self, nonce=NONCE_B):
        with patch('tools.audit_record_guarded_admission.secrets.token_hex',
                   return_value=nonce):
            return issue_guarded(self.db, self.anchor, now=FIXED_NOW + 1)

    def test_issue_against_bootstrap_anchor_is_atomic_and_private(self):
        self.assertEqual(self.new_issue(), NONCE_B)
        self.assertEqual(self.state(), (2, 0, 0))
        self.assertEqual(self.anchor.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(NONCE_A, str(_report(issued=True)))
        self.assertFalse(_report(issued=True)['checkpoint_updated_atomically_with_database'])
        self.assertTrue(_report(issued=True)['same_transaction_continuity_check_passed'])

    def test_accepted_capture_then_second_guarded_accept_rejected(self):
        self.assertTrue(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 2))
        self.assertFalse(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 3))
        self.assertEqual(self.state(), (1, 1, 2))

    def test_reused_streams_with_new_nonce_rolled_back(self):
        self.new_issue()
        self.assertTrue(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 2))
        self.assertFalse(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_B), now=FIXED_NOW + 3))
        self.assertEqual(self.state(), (2, 1, 2))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute(
                'SELECT consumed FROM challenges WHERE nonce=?',
                (NONCE_B,)).fetchone()[0], 0)

    def test_checkpoint_accept_and_detect_database_rollback(self):
        backup = self.verifier / 'pre-accept.sqlite'
        shutil.copyfile(self.db, backup)
        self.assertTrue(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 2))
        stronger = self.refresh_checkpoint('after-accept.json')
        self.anchor = stronger
        shutil.copyfile(backup, self.db)
        with self.assertRaises(ContinuityRegression):
            self.new_issue()
        with self.assertRaises(ContinuityRegression):
            accept_guarded(self.db, self.anchor, *fixture(NONCE_A),
                           now=FIXED_NOW + 3)
        self.assertEqual(self.state(), (1, 0, 0))

    def test_checkpoint_issued_history_regression_blocks_issue_and_accept(self):
        backup = self.verifier / 'before-issue.sqlite'
        shutil.copyfile(self.db, backup)
        self.new_issue()
        stronger = self.refresh_checkpoint('after-issue.json')
        self.anchor = stronger
        shutil.copyfile(backup, self.db)
        with self.assertRaises(ContinuityRegression):
            self.new_issue(NONCE_C)
        with self.assertRaises(ContinuityRegression):
            accept_guarded(self.db, self.anchor, *fixture(NONCE_A),
                           now=FIXED_NOW + 2)
        self.assertEqual(self.state(), (1, 0, 0))

    def test_record_modification_blocks_issue_without_touching_database(self):
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE challenges SET expires_at=expires_at+1')
        with self.assertRaises(ContinuityRegression):
            self.new_issue()
        self.assertEqual(self.state(), (1, 0, 0))

    def test_anchor_missing_or_malformed_blocks_both_operations(self):
        self.anchor.unlink()
        with self.assertRaises(FileNotFoundError):
            self.new_issue()
        with self.assertRaises(FileNotFoundError):
            accept_guarded(self.db, self.anchor, *fixture(NONCE_A),
                           now=FIXED_NOW + 2)
        self.assertEqual(self.state(), (1, 0, 0))
        self.anchor.write_bytes(b'{PRIVATE_0x80012345')
        with self.assertRaises(ValueError):
            self.new_issue()
        with self.assertRaises(ValueError):
            accept_guarded(self.db, self.anchor, *fixture(NONCE_A),
                           now=FIXED_NOW + 2)
        self.assertEqual(self.state(), (1, 0, 0))

    def test_symlink_checkpoint_and_public_checkpoint_refused(self):
        link = self.anchor_dir / 'symlink.json'
        link.symlink_to(self.anchor)
        with self.assertRaises(ValueError):
            issue_guarded(self.db, link, now=FIXED_NOW + 1)
        os.chmod(self.anchor, 0o644)
        with self.assertRaises(ValueError):
            self.new_issue()
        os.chmod(self.anchor, 0o600)
        self.assertEqual(self.state(), (1, 0, 0))

    def test_checkpoint_from_other_verifier_blocks_issue(self):
        second_dir = self.anchor_dir.parent / 'other-verifier'
        second_dir.mkdir(mode=0o700)
        second_db = second_dir / 'other.sqlite'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            legacy_issue(second_db, now=FIXED_NOW)
        foreign = self.refresh_checkpoint('unused-anchor.json')
        # Replace only the anchor with another verifier's snapshot.
        foreign.unlink()
        save_checkpoint(second_db, foreign)
        with self.assertRaises(ContinuityRegression):
            issue_guarded(self.db, foreign, now=FIXED_NOW + 1)

    def test_same_anchor_allows_multiple_new_issues_without_silent_reset(self):
        def create(_):
            return issue_guarded(self.db, self.anchor, now=FIXED_NOW + 2)
        with ThreadPoolExecutor(max_workers=5) as pool:
            issued = list(pool.map(create, range(5)))
        self.assertEqual(len(set(issued)), 5)
        self.assertEqual(self.state(), (6, 0, 0))

    def test_concurrent_accept_one_wins_and_second_not_consumed(self):
        evid = fixture(NONCE_A)
        def submit(_):
            return accept_guarded(self.db, self.anchor, *evid, now=FIXED_NOW + 2)
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(submit, range(6)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 5)
        self.assertEqual(self.state(), (1, 1, 2))

    def test_bad_capture_fails_without_spending_nonce(self):
        bad = list(fixture(NONCE_A))
        bad[4] = bad[4].replace(b'0x80120000', b'0x80120010', 1)
        with self.assertRaises(ValueError):
            accept_guarded(self.db, self.anchor, *bad, now=FIXED_NOW + 2)
        self.assertEqual(self.state(), (1, 0, 0))
        self.assertTrue(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 3))

    def test_expired_challenge_and_clock_rollback_rejected(self):
        self.assertFalse(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW - 1))
        self.assertFalse(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 300))
        self.assertEqual(self.state(), (1, 0, 0))

    def test_rollback_after_unique_digest_collision(self):
        self.new_issue()
        self.assertTrue(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_A), now=FIXED_NOW + 2))
        self.assertFalse(accept_guarded(
            self.db, self.anchor, *fixture(NONCE_B), now=FIXED_NOW + 2))
        self.assertEqual(self.state(), (2, 1, 2))

    def test_corrupt_database_fails_closed(self):
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE challenges SET consumed=1')
        with self.assertRaises(ValueError):
            self.new_issue()
        with self.assertRaises(ValueError):
            accept_guarded(self.db, self.anchor, *fixture(NONCE_A),
                           now=FIXED_NOW + 2)
        self.assertEqual(self.state(), (1, 0, 0))

    def test_cli_guarded_issue_and_redacted_failure(self):
        stdout = io.StringIO()
        with patch('tools.audit_record_guarded_admission.secrets.token_hex',
                   return_value=NONCE_B), patch(
                   'tools.audit_record_guarded_admission.time.time',
                   return_value=FIXED_NOW + 1), contextlib.redirect_stdout(stdout):
            exitcode = main(['issue', str(self.db), str(self.anchor)])
        self.assertEqual(exitcode, 0)
        response = json.loads(stdout.getvalue())
        self.assertEqual(response['session_nonce'], NONCE_B)
        self.assertFalse(response['external_checkpoint_independently_authenticated'])
        with sqlite3.connect(self.db) as c:
            c.execute('DELETE FROM challenges WHERE nonce=?', (NONCE_A,))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exitcode = main(['issue', str(self.db), str(self.anchor)])
        self.assertEqual(exitcode, 1)
        self.assertTrue(json.loads(stdout.getvalue())[
            'historical_checkpoint_regression_detected'])
        self.assertNotIn(NONCE_A, stdout.getvalue())
        self.assertNotIn(NONCE_B, stdout.getvalue())

    def test_cli_guarded_accept_and_invalid_private_error(self):
        evid = fixture(NONCE_A)
        with tempfile.TemporaryDirectory() as root:
            inventory = Path(root) / 'inventory.json'
            inventory.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'directory': False}]}))
            paths = [Path(root) / ('PRIVATE_' + str(i) + '.json')
                     for i in range(7)]
            for p, content in zip(paths, evid[1:]):
                p.write_bytes(content)
            argv = ['accept', str(self.db), str(self.anchor),
                    '/private/WildArms.bin', str(inventory),
                    *[str(p) for p in paths]]
            def run():
                stdout = io.StringIO()
                with patch('tools.audit_record_guarded_admission.read_raw_iso_entry',
                           return_value=evid[0]), patch(
                           'tools.audit_record_guarded_admission.time.time',
                           return_value=FIXED_NOW + 2), contextlib.redirect_stdout(stdout):
                    code = main(argv)
                return code, stdout.getvalue()
            code, output = run()
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)['guarded_acceptance_committed'])
            self.assertNotIn(NONCE_A, output)
            self.assertNotIn('PRIVATE_', output)
            code, output = run()
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)['guarded_acceptance_committed'])
            paths[-1].write_bytes(b'{PRIVATE_REPLAY_0x8000000')
            code, output = run()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_REPLAY_', output)


if __name__ == '__main__':
    unittest.main()
