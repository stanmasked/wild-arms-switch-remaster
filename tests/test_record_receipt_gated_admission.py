"""Synthetic-only regression tests for stage-249 custodian-receipt admission."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
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
from tools.audit_record_anchor_handoff import (
    deposit, deliver_receipt, export_latest,
)
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_receipt_gated_admission import (
    AnchorConflict, PendingHandoff, _report,
    bootstrap, issue, accept, acknowledge, main,
)

NONCE_C = 'fedcba9876543210fedcba9876543210'


class ReceiptGatedAdmissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.verifier_dir = base / 'verifier'
        self.custodian_dir = base / 'custodian'
        self.verifier_dir.mkdir(mode=0o700)
        self.custodian_dir.mkdir(mode=0o700)
        self.db = self.verifier_dir / 'capture.sqlite'
        self.custody = self.custodian_dir / 'anchors.sqlite'
        self.checkpoint_counter = 0
        self.receipt_counter = 0
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            legacy_issue(self.db, now=FIXED_NOW)
        self.commit_snapshot()
        bootstrap(self.db, self.custody, self.receipt)

    def commit_snapshot(self):
        self.checkpoint_counter += 1
        offer = self.verifier_dir / ('offer-%d.json' % self.checkpoint_counter)
        save_checkpoint(self.db, offer)
        seq, new = deposit(self.custody, offer.read_bytes())
        self.receipt_counter += 1
        private = self.custodian_dir / ('receipt-%d.json' % self.receipt_counter)
        deliver_receipt(self.custody, private)
        self.receipt = private.read_bytes()
        self.receipt_path = private
        return seq, new

    def guarded_issue(self, nonce=NONCE_B):
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=nonce):
            return issue(self.db, self.custody, self.receipt, now=FIXED_NOW+2)

    def guarded_accept(self, nonce=NONCE_A):
        return accept(self.db, self.custody, self.receipt, *fixture(nonce),
                      now=FIXED_NOW+3)

    def table(self):
        with sqlite3.connect(self.db) as con:
            row = con.execute(
                'SELECT ack_sequence,ack_receipt_sha256,pending_sequence,'
                'pending_checkpoint_sha256 FROM receipt_gate').fetchone()
            return row

    def counts(self):
        with sqlite3.connect(self.db) as con:
            return (con.execute('SELECT COUNT(*) FROM challenges').fetchone()[0],
                    con.execute('SELECT COUNT(*) FROM accepted').fetchone()[0])

    def test_initial_bootstrap_matches_external_checkpoint_exactly(self):
        row = self.table()
        self.assertEqual(row[0], 1)
        self.assertIsNone(row[2])
        self.assertEqual(self.counts(), (1, 0))
        self.assertFalse(_report(bootstrapped=True)[
            'independent_custodian_identity_authenticated'])

    def test_bootstrap_only_once_without_reset(self):
        with self.assertRaises(ValueError):
            bootstrap(self.db, self.custody, self.receipt)
        self.assertEqual(self.table()[0], 1)

    def test_bootstrap_rejects_unanchored_local_changes(self):
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE challenges SET expires_at=expires_at+1')
        with self.assertRaises(AnchorConflict):
            bootstrap(self.db, self.custody, self.receipt)

    def test_issue_marks_pending_and_blocks_next_issue_and_accept(self):
        self.assertEqual(self.guarded_issue(), NONCE_B)
        self.assertEqual(self.table()[2], 2)
        with self.assertRaises(PendingHandoff):
            self.guarded_issue(NONCE_C)
        with self.assertRaises(PendingHandoff):
            self.guarded_accept()
        self.assertEqual(self.counts(), (2, 0))

    def test_no_ack_before_custodian_durable_deposit(self):
        self.guarded_issue()
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, self.receipt)
        self.assertEqual(self.table()[2], 2)

    def test_commit_then_deposit_then_ack_releases_next_operation(self):
        self.guarded_issue()
        self.assertEqual(self.commit_snapshot(), (2, True))
        self.assertTrue(acknowledge(self.db, self.custody, self.receipt))
        self.assertIsNone(self.table()[2])
        self.assertEqual(self.table()[0], 2)
        # The nonce existed before this acceptance and is still fresh.
        self.assertTrue(self.guarded_accept(NONCE_A))
        self.assertEqual(self.table()[2], 3)
        self.assertEqual(self.counts(), (2, 1))

    def test_ack_idempotent_after_crash(self):
        self.guarded_issue()
        self.commit_snapshot()
        self.assertTrue(acknowledge(self.db, self.custody, self.receipt))
        self.assertFalse(acknowledge(self.db, self.custody, self.receipt))
        self.assertIsNone(self.table()[2])

    def test_crash_after_deposit_before_receipt_file_recovers(self):
        self.guarded_issue()
        self.checkpoint_counter += 1
        offer = self.verifier_dir / ('offer-%d.json' % self.checkpoint_counter)
        save_checkpoint(self.db, offer)
        self.assertEqual(deposit(self.custody, offer.read_bytes()), (2, True))
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, self.receipt)
        self.receipt_counter += 1
        recovered = self.custodian_dir / ('recovered-%d.json' % self.receipt_counter)
        self.assertEqual(deliver_receipt(self.custody, recovered), 2)
        self.assertTrue(acknowledge(self.db, self.custody, recovered.read_bytes()))
        self.assertIsNone(self.table()[2])

    def test_stale_receipt_refused_after_custodian_deposit(self):
        previous = self.receipt
        self.guarded_issue()
        self.commit_snapshot()
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, previous)
        self.assertTrue(acknowledge(self.db, self.custody, self.receipt))

    def test_receipt_modified_digest_is_rejected(self):
        self.guarded_issue()
        self.commit_snapshot()
        tampered = json.loads(self.receipt)
        tampered['checkpoint_sha256'] = 'd' * 64
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, json.dumps(tampered).encode())
        self.assertEqual(self.table()[2], 2)

    def test_repeated_receipt_after_pending_matches_not_accepted_as_new_round(self):
        self.guarded_issue()
        self.commit_snapshot()
        self.assertTrue(acknowledge(self.db, self.custody, self.receipt))
        self.assertFalse(acknowledge(self.db, self.custody, self.receipt))
        self.assertEqual(self.table()[0], 2)

    def test_modified_pending_db_is_not_acknowledged(self):
        self.guarded_issue()
        before_legacy = self.verifier_dir / 'pending-before-legacy.sqlite'
        shutil.copyfile(self.db, before_legacy)
        with self.checkpoint_lock():
            with sqlite3.connect(self.db) as con:
                con.execute('UPDATE challenges SET expires_at=expires_at+1'
                            ' WHERE nonce=?', (NONCE_B,))
        self.commit_snapshot()
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, self.receipt)
        self.assertEqual(self.table()[2], 2)
        # Restoring the exact pending state also exposes the post-deposit
        # custodian snapshot mismatch rather than silently consuming it.
        shutil.copyfile(before_legacy, self.db)
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, self.receipt)

    def checkpoint_lock(self):
        return contextlib.nullcontext()

    def test_restored_database_before_pending_cannot_ignore_advanced_custodian(self):
        prior_db = self.verifier_dir / 'prior.sqlite'
        shutil.copyfile(self.db, prior_db)
        self.guarded_issue()
        self.commit_snapshot()
        shutil.copyfile(prior_db, self.db)
        with self.assertRaises(AnchorConflict):
            self.guarded_issue(NONCE_C)
        with self.assertRaises(AnchorConflict):
            acknowledge(self.db, self.custody, self.receipt)
        self.assertIsNone(self.table()[2])

    def test_concurrent_issues_only_one_can_leave_pending(self):
        def contender(i):
            try:
                return self.guarded_issue(
                    NONCE_B if i == 0 else __import__('secrets').token_hex(16))
            except PendingHandoff:
                return None
        with ThreadPoolExecutor(max_workers=5) as pool:
            outcomes = list(pool.map(contender, range(5)))
        self.assertEqual(sum(value is not None for value in outcomes), 1)
        self.assertEqual(self.counts(), (2, 0))
        self.assertEqual(self.table()[2], 2)

    def test_stage_243_tampering_does_not_spend_nonce(self):
        damaged = list(fixture(NONCE_A))
        damaged[4] = damaged[4].replace(b'0x80120000',
                                        b'0x80120010', 1)
        with self.assertRaises(ValueError):
            accept(self.db, self.custody, self.receipt, *damaged,
                   now=FIXED_NOW+1)
        self.assertEqual(self.counts(), (1, 0))
        self.assertIsNone(self.table()[2])
        self.assertTrue(self.guarded_accept())

    def test_expired_or_missing_nonce_keeps_gate_ready(self):
        self.assertFalse(accept(self.db, self.custody, self.receipt,
                                *fixture(NONCE_A), now=FIXED_NOW+300))
        self.assertFalse(accept(self.db, self.custody, self.receipt,
                                *fixture(NONCE_B), now=FIXED_NOW+1))
        self.assertIsNone(self.table()[2])
        self.assertEqual(self.counts(), (1, 0))

    def test_no_gate_or_corrupted_guard_fails_closed(self):
        with sqlite3.connect(self.db) as con:
            con.execute('DELETE FROM receipt_gate')
        with self.assertRaises(ValueError):
            self.guarded_issue()
        with self.assertRaises(ValueError):
            self.guarded_accept()
        self.assertEqual(self.counts(), (1, 0))

    def test_independent_custodian_rollback_is_detected_relative_to_guard(self):
        custodian_old = self.custodian_dir / 'old.sqlite'
        shutil.copyfile(self.custody, custodian_old)
        self.guarded_issue()
        self.commit_snapshot()
        self.assertTrue(acknowledge(self.db, self.custody, self.receipt))
        shutil.copyfile(custodian_old, self.custody)
        # The new/latest receipt cannot be verified against the old custody.
        with self.assertRaises(AnchorConflict):
            self.guarded_issue()
        # Nor can the old receipt satisfy the verifier's newest high-water.
        prev_file = self.custodian_dir / 'receipt-1.json'
        with self.assertRaises(AnchorConflict):
            issue(self.db, self.custody, prev_file.read_bytes(),
                  now=FIXED_NOW+4)

    def test_cli_bootstrap_rejects_repeat_privately(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['bootstrap', str(self.db), str(self.custody),
                         str(self.receipt_path)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'],
                         'invalid_private_input')
        self.assertNotIn(NONCE_A, out.getvalue())

    def test_cli_issue_ack_and_privacy(self):
        out = io.StringIO()
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=NONCE_B), patch(
                   'tools.audit_record_guarded_admission.time.time',
                   return_value=FIXED_NOW+2), contextlib.redirect_stdout(out):
            code = main(['issue', str(self.db), str(self.custody),
                         str(self.receipt_path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['session_nonce'], NONCE_B)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['issue', str(self.db), str(self.custody),
                         str(self.receipt_path)])
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(out.getvalue())['further_admission_blocked'])
        self.assertNotIn(NONCE_B, out.getvalue())
        self.commit_snapshot()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['ack', str(self.db), str(self.custody),
                         str(self.receipt_path)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())[
            'custodian_acknowledgment_recorded'])
        self.assertNotIn(NONCE_B, out.getvalue())

    def test_cli_accept_then_ack_and_redacted_invalid_evidence(self):
        evid = fixture(NONCE_A)
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / 'inventory.json'
            inventory.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'directory': False}]}))
            paths = [Path(tmp) / ('PRIVATE_EVIDENCE_%d.json' % i)
                     for i in range(7)]
            for path, raw in zip(paths, evid[1:]):
                path.write_bytes(raw)
            args = ['accept', str(self.db), str(self.custody),
                    str(self.receipt_path), '/private/WildArms.bin',
                    str(inventory), *[str(p) for p in paths]]
            def run():
                out = io.StringIO()
                with patch('tools.audit_record_receipt_gated_admission.read_raw_iso_entry',
                           return_value=evid[0]), patch(
                           'tools.audit_record_guarded_admission.time.time',
                           return_value=FIXED_NOW+3), contextlib.redirect_stdout(out):
                    status = main(args)
                return status, out.getvalue()
            status, output = run()
            self.assertEqual(status, 0)
            self.assertTrue(json.loads(output)['capture_accepted_with_pending_anchor'])
            self.assertNotIn(NONCE_A, output)
            self.assertNotIn('/private/', output)
            status, output = run()
            self.assertEqual(status, 1)
            self.assertTrue(json.loads(output)['further_admission_blocked'])
            self.commit_snapshot()
            self.assertTrue(acknowledge(self.db, self.custody, self.receipt))
            paths[-1].write_bytes(b'{PRIVATE_MEMORY_0x800d')
            status, output = run()
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output)['error_code'],
                             'invalid_private_input')
            self.assertNotIn('PRIVATE_MEMORY', output)


if __name__ == '__main__':
    unittest.main()
