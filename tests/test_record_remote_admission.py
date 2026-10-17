"""Synthetic local-loopback tests of remote admission without custodian DB copy."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import ssl
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import fixture, NONCE_A, NONCE_B, FIXED_NOW
from tests.test_record_custodian_tls import MutualTlsCustodianTests as TLSFixture
from tools.audit_record_receipt_gated_admission import PendingHandoff, AnchorConflict
from tools.audit_record_anchor_handoff import _read_latest
from tools.audit_record_remote_admission import (
    _remote_head, bootstrap_remote, issue_remote, accept_remote,
    acknowledge_remote, main,
)

NONCE_C = 'fedcba9876543210fedcba9876543210'


class RemoteCustodyAdmissionTests(unittest.TestCase):
    # Reuse exactly the synthetic TLS server and temporary test keys without
    # repeating base test methods in unittest discovery.
    make_offer_and_deposit = TLSFixture.make_offer_and_deposit
    new_offer = TLSFixture.new_offer
    run_channel = TLSFixture.run_channel

    @classmethod
    def setUpClass(cls):
        TLSFixture.setUpClass()
        for field in ('ca', 'server_key', 'server_cert', 'server_pin',
                      'client_key', 'client_cert', 'client_pin',
                      'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, field, getattr(TLSFixture, field))

    @classmethod
    def tearDownClass(cls):
        TLSFixture.tearDownClass()

    def setUp(self):
        TLSFixture.setUp(self)
        self.remote = self._channel
        bootstrap_remote(self.verifier, self.remote, self.sign_pub,
                         self.sign_pub_pin, tag=self.tag)

    def _channel(self, *, action, checkpoint_raw,
                 expected_sequence=None, expected_receipt_sha256=None):
        expected = ((expected_sequence, expected_receipt_sha256)
                    if expected_sequence is not None else None)
        response, _ = self.run_channel(
            action=action, checkpoint=checkpoint_raw, expected_head=expected)
        return response

    def issue(self, nonce=NONCE_B):
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=nonce):
            return issue_remote(self.verifier, self.remote, self.sign_pub,
                                self.sign_pub_pin, tag=self.tag, now=FIXED_NOW+1)

    def accept(self, nonce=NONCE_A):
        return accept_remote(
            self.verifier, self.remote, self.sign_pub, self.sign_pub_pin,
            *fixture(nonce), tag=self.tag, now=FIXED_NOW+2)

    def ack(self):
        return acknowledge_remote(
            self.verifier, self.remote, self.sign_pub,
            self.sign_pub_pin, tag=self.tag)

    def state(self):
        with sqlite3.connect(self.verifier) as con:
            counts = (
                con.execute('SELECT COUNT(*) FROM challenges').fetchone()[0],
                con.execute('SELECT COUNT(*) FROM accepted').fetchone()[0],
                con.execute('SELECT COUNT(*) FROM accepted_streams').fetchone()[0],
            )
            seq = con.execute(
                'SELECT ack_sequence,pending_sequence FROM receipt_gate').fetchone()
        return counts, seq

    def test_bootstrap_receipt_gate_without_local_custodian_db_path(self):
        self.assertEqual(self.state(), ((1, 0, 0), (1, None)))
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_issue_then_remote_deposit_ack_then_capture(self):
        self.assertEqual(self.issue(), NONCE_B)
        self.assertEqual(self.state(), ((2, 0, 0), (1, 2)))
        with self.assertRaises(PendingHandoff):
            self.issue(NONCE_C)
        with self.assertRaises(PendingHandoff):
            self.accept()
        self.assertTrue(self.ack())
        self.assertEqual(self.state(), ((2, 0, 0), (2, None)))
        self.assertTrue(self.accept())
        self.assertEqual(self.state(), ((2, 1, 2), (2, 3)))
        self.assertTrue(self.ack())
        self.assertEqual(self.state(), ((2, 1, 2), (3, None)))
        self.assertFalse(self.ack())

    def test_pending_checkpoint_committed_before_disconnection(self):
        self.issue()
        original = self.remote
        def offline(*, action, checkpoint_raw,
                    expected_sequence=None, expected_receipt_sha256=None):
            raise OSError('network disconnection')
        self.remote = offline
        with self.assertRaises(OSError):
            self.ack()
        self.assertEqual(self.state(), ((2, 0, 0), (1, 2)))
        self.remote = original
        self.assertTrue(self.ack())

    def test_after_deposit_before_response_loss_is_idempotent(self):
        self.issue()
        import tools.audit_record_custodian_tls as ch
        action = ch._process
        def process_then_disconnect(*args):
            action(*args)
            raise OSError('simulated TCP loss after custodian commit')
        with patch('tools.audit_record_custodian_tls._process',
                   side_effect=process_then_disconnect):
            with self.assertRaises((OSError, ValueError, ssl.SSLError)):
                self.ack()
        self.assertEqual(self.state()[1], (1, 2))
        self.assertEqual(_read_latest(self.custody)[0], 2)
        self.assertTrue(self.ack())
        self.assertEqual(_read_latest(self.custody)[0], 2)

    def test_acknowledgment_response_loss_is_recoverable(self):
        self.issue()
        self.assertTrue(self.ack())
        self.assertFalse(self.ack())
        self.assertEqual(self.state()[1], (2, None))

    def test_bad_signing_key_pin_fails_without_issuing(self):
        with self.assertRaisesRegex(ValueError, 'pin mismatch'):
            issue_remote(self.verifier, self.remote, self.sign_pub,
                         'f'*64, tag=self.tag, now=FIXED_NOW+1)
        self.assertEqual(self.state(), ((1, 0, 0), (1, None)))

    def test_bad_custodian_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            issue_remote(self.verifier, self.remote, self.sign_pub,
                         self.sign_pub_pin, tag='wrong-one',
                         now=FIXED_NOW+1)
        self.assertEqual(self.state(), ((1, 0, 0), (1, None)))

    def test_conflicting_authenticated_remote_checkpoint_blocks_admission(self):
        self.issue()
        self.ack()
        # Simulate stale verifier DB; the remote custodian is ahead.
        backup = self.v / 'state-after-first-round.sqlite'
        shutil.copyfile(self.verifier, backup)
        self.issue(NONCE_C)
        self.ack()
        shutil.copyfile(backup, self.verifier)
        with self.assertRaises(AnchorConflict):
            self.issue()
        self.assertEqual(self.state()[1], (2, None))

    def test_external_advance_blocks_old_verifier_high_water(self):
        new = self.new_offer()
        self.run_channel(action='deposit', checkpoint=new)
        with self.assertRaises(AnchorConflict):
            self.issue()
        self.assertEqual(self.state()[1], (1, None))

    def test_pending_tamper_prevents_custodian_deposit(self):
        self.issue()
        with sqlite3.connect(self.verifier) as con:
            con.execute(
                'UPDATE challenges SET expires_at=expires_at+1 WHERE nonce=?',
                (NONCE_B,))
        with self.assertRaises(AnchorConflict):
            self.ack()
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_bogus_network_reply_not_accepted_even_when_signed_fixture_exists(self):
        _, good_sig, seq = self.remote(action='latest', checkpoint_raw=None)
        def bad_channel(*, action, checkpoint_raw,
                        expected_sequence=None, expected_receipt_sha256=None):
            return b'not a valid checkpoint', good_sig, seq
        with self.assertRaises(ValueError):
            issue_remote(self.verifier, bad_channel, self.sign_pub,
                         self.sign_pub_pin, tag=self.tag,
                         now=FIXED_NOW+1)
        self.assertEqual(self.state()[0], (1, 0, 0))

    def test_concurrent_issues_only_one_can_pending(self):
        def attempt(i):
            try:
                return issue_remote(
                    self.verifier, self.remote, self.sign_pub,
                    self.sign_pub_pin, tag=self.tag, now=FIXED_NOW+1)
            except PendingHandoff:
                return None
        with ThreadPoolExecutor(max_workers=3) as pool:
            # Each remote attempt needs a separate serve_one in TLSFixture.
            # Python socket bound inside run_channel supports this.
            result = list(pool.map(attempt, range(3)))
        self.assertEqual(sum(x is not None for x in result), 1)
        self.assertEqual(self.state()[0], (2, 0, 0))

    def test_cli_missing_tls_channel_reports_redacted_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main([
                'issue', str(self.verifier), '127.0.0.1', '9', 'localhost',
                str(self.client_cert), str(self.client_key), str(self.ca),
                self.server_pin, str(self.sign_pub), self.sign_pub_pin,
                '--custodian-tag', self.tag])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'],
                         'invalid_private_input_or_remote_custodian')
        self.assertNotIn(self.sign_pub_pin, out.getvalue())


if __name__ == '__main__':
    unittest.main()
