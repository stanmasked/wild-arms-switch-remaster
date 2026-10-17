"""Synthetic-only tests for durable stage-248 custodian checkpoint handoff."""
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

from tests.test_record_atomic_verifier import fixture, NONCE_A, NONCE_B, FIXED_NOW
from tools.audit_record_atomic_verifier import issue, accept
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_anchor_handoff import (
    RECEIPT_SCHEMA, REPORT_SCHEMA, HandoffRegression,
    MAX_RECEIPT_BYTES, MAX_ROUNDS,
    deposit, deliver_receipt, export_latest, verify_receipt, main,
)


class CustodianHandoffTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.local = self.root / 'verifier'
        self.remote = self.root / 'custodian'
        self.local.mkdir(mode=0o700)
        self.remote.mkdir(mode=0o700)
        self.verifier = self.local / 'sessions.sqlite'
        self.custodian = self.remote / 'custody.sqlite'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            issue(self.verifier, now=FIXED_NOW)
        self.first_path = self.local / 'first.json'
        save_checkpoint(self.verifier, self.first_path)
        self.first = self.first_path.read_bytes()

    def second(self):
        self.assertTrue(accept(self.verifier, *fixture(NONCE_A),
                               now=FIXED_NOW+1))
        dst = self.local / 'second.json'
        save_checkpoint(self.verifier, dst)
        return dst.read_bytes()

    def issue_second(self):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            issue(self.verifier, now=FIXED_NOW+2)
        dst = self.local / 'next.json'
        save_checkpoint(self.verifier, dst)
        return dst.read_bytes()

    def test_first_deposit_then_receipt_recovery(self):
        self.assertEqual(deposit(self.custodian, self.first), (1, True))
        receipt = self.remote / 'receipt-1.json'
        # Simulate a crash/restart between COMMIT and receipt output:
        # receipt can be issued later solely from durable custodian state.
        self.assertEqual(deliver_receipt(self.custodian, receipt), 1)
        private = receipt.read_bytes()
        self.assertEqual(json.loads(private)['schema'], RECEIPT_SCHEMA)
        self.assertEqual(json.loads(private)['sequence'], 1)
        self.assertTrue(verify_receipt(self.custodian, private))
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(NONCE_A, private.decode())
        self.assertNotIn(NONCE_A, str((1, True)))

    def test_duplicate_latest_deposit_is_idempotent(self):
        self.assertEqual(deposit(self.custodian, self.first), (1, True))
        self.assertEqual(deposit(self.custodian, self.first), (1, False))
        with sqlite3.connect(self.custodian) as c:
            self.assertEqual(c.execute(
                'SELECT COUNT(*) FROM anchor_history').fetchone()[0], 1)

    def test_second_deposit_chains_prior_receipt(self):
        deposit(self.custodian, self.first)
        second = self.second()
        self.assertEqual(deposit(self.custodian, second), (2, True))
        output = self.remote / 'second-receipt.json'
        deliver_receipt(self.custodian, output)
        value = json.loads(output.read_bytes())
        self.assertEqual(value['sequence'], 2)
        self.assertNotEqual(value['previous_receipt_sha256'], '0'*64)
        self.assertTrue(verify_receipt(self.custodian, output.read_bytes()))
        self.assertEqual(value['checkpoint_sha256'],
                         __import__('hashlib').sha256(second).hexdigest())

    def test_old_receipt_is_not_current(self):
        deposit(self.custodian, self.first)
        old = self.remote / 'receipt-first.json'
        deliver_receipt(self.custodian, old)
        self.assertTrue(verify_receipt(self.custodian, old.read_bytes()))
        deposit(self.custodian, self.second())
        self.assertFalse(verify_receipt(self.custodian, old.read_bytes()))

    def test_old_offer_cannot_displace_newer_state(self):
        deposit(self.custodian, self.first)
        deposit(self.custodian, self.second())
        with self.assertRaises(HandoffRegression):
            deposit(self.custodian, self.first)
        with sqlite3.connect(self.custodian) as c:
            self.assertEqual(c.execute(
                'SELECT COUNT(*) FROM anchor_history').fetchone()[0], 2)

    def test_same_counts_but_different_verifier_rejected(self):
        deposit(self.custodian, self.first)
        with tempfile.TemporaryDirectory() as another:
            second_db = Path(another) / 'other.sqlite'
            with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                       return_value=NONCE_B):
                issue(second_db, now=FIXED_NOW)
            other_checkpoint = Path(another) / 'other.json'
            save_checkpoint(second_db, other_checkpoint)
            with self.assertRaises(HandoffRegression):
                deposit(self.custodian, other_checkpoint.read_bytes())

    def test_privately_exported_committed_checkpoint_identical(self):
        deposit(self.custodian, self.first)
        export = self.remote / 'latest.json'
        self.assertEqual(export_latest(self.custodian, export), 1)
        self.assertEqual(export.read_bytes(), self.first)
        self.assertEqual(export.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            export_latest(self.custodian, export)
        self.assertEqual(export.read_bytes(), self.first)

    def test_deposit_crash_before_receipt_then_replay_is_safe(self):
        deposit(self.custodian, self.first)
        with patch('tools.audit_record_anchor_handoff._write_new_private',
                   side_effect=OSError('simulated private storage outage')):
            with self.assertRaises(OSError):
                deliver_receipt(self.custodian, self.remote / 'receipt.json')
        self.assertEqual(deposit(self.custodian, self.first), (1, False))
        receipt_path = self.remote / 'retry.json'
        self.assertEqual(deliver_receipt(self.custodian, receipt_path), 1)
        self.assertTrue(verify_receipt(self.custodian, receipt_path.read_bytes()))

    def test_corrupted_custodian_chain_fails_closed(self):
        deposit(self.custodian, self.first)
        with sqlite3.connect(self.custodian) as c:
            c.execute('UPDATE anchor_history SET previous_receipt_sha256=?',
                      ('f'*64,))
        with self.assertRaisesRegex(ValueError, 'sequence'):
            deliver_receipt(self.custodian, self.remote / 'receipt.json')
        with self.assertRaises(ValueError):
            deposit(self.custodian, self.first)

    def test_corrupted_checkpoint_blob_fails_closed(self):
        deposit(self.custodian, self.first)
        with sqlite3.connect(self.custodian) as c:
            c.execute('UPDATE anchor_history SET checkpoint_bytes=?',
                      (sqlite3.Binary(b'corruption'),))
        with self.assertRaisesRegex(ValueError, 'corrupted'):
            export_latest(self.custodian, self.remote / 'out.json')

    def test_missing_sequence_after_second_deposit_rejected(self):
        deposit(self.custodian, self.first)
        deposit(self.custodian, self.second())
        with sqlite3.connect(self.custodian) as c:
            c.execute('DELETE FROM anchor_history WHERE sequence=1')
        with self.assertRaises(ValueError):
            deliver_receipt(self.custodian, self.remote / 'receipt.json')

    def test_concurrent_duplicate_deposit_only_one_new_entry(self):
        def submit(_):
            return deposit(self.custodian, self.first)
        with ThreadPoolExecutor(max_workers=5) as pool:
            statuses = list(pool.map(submit, range(5)))
        self.assertEqual(sum(new for _, new in statuses), 1)
        self.assertTrue(all(seq == 1 for seq, _ in statuses))

    def test_private_receipt_duplicate_keys_wrong_types_and_size(self):
        deposit(self.custodian, self.first)
        dst = self.remote / 'receipt.json'
        deliver_receipt(self.custodian, dst)
        good = json.loads(dst.read_bytes())
        for bad in (
            b'',
            b'{' + b'"schema":"a","schema":"b"}',
            json.dumps({**good, 'sequence': True}).encode(),
            json.dumps({**good, 'sequence': 0}).encode(),
            json.dumps({**good, 'checkpoint_sha256': 'X'*64}).encode(),
            json.dumps({**good, 'extra': 'PRIVATE'}).encode(),
            b'x'*(MAX_RECEIPT_BYTES+1),
        ):
            with self.subTest(bad=bad[:22]):
                with self.assertRaises(ValueError):
                    verify_receipt(self.custodian, bad)

    def test_single_modified_receipt_detected_without_leaking(self):
        deposit(self.custodian, self.first)
        dst = self.remote / 'receipt.json'
        deliver_receipt(self.custodian, dst)
        value = json.loads(dst.read_bytes())
        value['checkpoint_sha256'] = 'd'*64
        self.assertFalse(verify_receipt(self.custodian,
                                        json.dumps(value).encode()))

    def test_nonprivate_or_symlink_source_refused_by_cli(self):
        offer = self.local / 'shortcut.json'
        offer.symlink_to(self.first_path)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['deposit', str(self.custodian), str(offer)])
        self.assertEqual(code, 2)
        self.assertFalse(self.custodian.exists())
        self.assertNotIn(NONCE_A, out.getvalue())
        os.chmod(self.first_path, 0o644)
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(['deposit', str(self.custodian), str(self.first_path)])
        self.assertEqual(code, 2)

    def test_cli_prepare_deposit_receipt_verify_and_export(self):
        second_offer = self.local / 'prepared.json'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['prepare', str(self.verifier),
                                   str(second_offer)]), 0)
        self.assertTrue(json.loads(out.getvalue())['private_checkpoint_prepared'])
        self.assertNotIn(NONCE_A, out.getvalue())
        for args, expected in (
            (['deposit', str(self.custodian), str(second_offer)],
             'custodian_commit_recorded'),
            (['receipt', str(self.custodian),
              str(self.remote/'receipt.json')], 'private_receipt_created'),
            (['verify', str(self.custodian),
              str(self.remote/'receipt.json')], 'latest_receipt_matches_custodian'),
            (['export', str(self.custodian),
              str(self.remote/'latest.json')], 'private_checkpoint_exported'),
        ):
            with self.subTest(args=args):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = main(args)
                self.assertEqual(code, 0)
                self.assertTrue(json.loads(out.getvalue())[expected])
                self.assertNotIn(NONCE_A, out.getvalue())
                self.assertNotIn('PRIVATE_', out.getvalue())
        self.assertEqual((self.remote/'latest.json').read_bytes(),
                         second_offer.read_bytes())

    def test_cli_stale_deposit_returns_redacted_rejection(self):
        deposit(self.custodian, self.first)
        deposit(self.custodian, self.second())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['deposit', str(self.custodian), str(self.first_path)])
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(out.getvalue())[
            'custodian_handoff_regression_detected'])
        self.assertNotIn(NONCE_A, out.getvalue())

    def test_cli_invalid_receipt_generic_error(self):
        deposit(self.custodian, self.first)
        bad = self.remote / 'bad.json'
        bad.write_bytes(b'{PRIVATE_HASH_0x80100000')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['verify', str(self.custodian), str(bad)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'],
                         'invalid_private_input')
        self.assertNotIn('PRIVATE_HASH', out.getvalue())


if __name__ == '__main__':
    unittest.main()
