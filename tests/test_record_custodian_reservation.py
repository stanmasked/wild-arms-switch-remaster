"""Synthetic mutually authenticated pre-issue custody reservation tests."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import shutil
import sqlite3
import ssl
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import NONCE_A, NONCE_B, FIXED_NOW
from tests.test_record_custodian_tls import MutualTlsCustodianTests as TLSFixture
from tools.audit_record_remote_admission import bootstrap_remote
from tools.audit_record_remote_reserved_issue import (
    _intent, issue_reserved, acknowledge_reserved, main,
)
from tools.audit_record_custodian_reservation import (
    reserve, reservation_row, ReservationConflict,
)
from tools.audit_record_anchor_handoff import _read_latest
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_receipt_gated_admission import PendingHandoff, AnchorConflict

NONCE_C = 'fedcba9876543210fedcba9876543210'


class ReservedIssueTests(unittest.TestCase):
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
        self.transport = self._channel
        bootstrap_remote(self.verifier, self.transport, self.sign_pub,
                         self.sign_pub_pin, tag=self.tag)

    def _channel(self, *, action, checkpoint_raw, expected_sequence=None,
                 expected_receipt_sha256=None, reservation_token=None):
        expected = ((expected_sequence, expected_receipt_sha256)
                    if expected_sequence is not None else None)
        response, _ = self.run_channel(
            action=action, checkpoint=checkpoint_raw,
            expected_head=expected, reservation_token=reservation_token)
        return response

    def new_issue(self, nonce=NONCE_B):
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=nonce):
            return issue_reserved(
                self.verifier, self.transport, self.sign_pub,
                self.sign_pub_pin, tag=self.tag, now=FIXED_NOW+1)

    def ack(self):
        return acknowledge_reserved(
            self.verifier, self.transport, self.sign_pub,
            self.sign_pub_pin, tag=self.tag)

    def intent(self):
        with sqlite3.connect(self.verifier) as con:
            return _intent(con)

    def head(self):
        return _read_latest(self.custody)

    def offered(self):
        p = self.v / 'pending-reserved.json'
        save_checkpoint(self.verifier, p)
        return p.read_bytes()

    def state(self):
        with sqlite3.connect(self.verifier) as con:
            return (
                con.execute('SELECT COUNT(*) FROM challenges').fetchone()[0],
                con.execute('SELECT ack_sequence,pending_sequence'
                            ' FROM receipt_gate').fetchone(),
            )

    def test_issue_reserves_before_creating_nonce_then_ack(self):
        self.assertEqual(self.new_issue(), NONCE_B)
        self.assertEqual(self.state(), (2, (1, 2)))
        row = self.intent()
        self.assertEqual((row[1], row[2]), (1, self.head()[3]))
        with sqlite3.connect(self.custody) as con:
            owner = reservation_row(con)
        self.assertEqual(owner[4], 'reserved')
        self.assertTrue(self.ack())
        self.assertEqual(self.state(), (2, (2, None)))
        with sqlite3.connect(self.custody) as con:
            committed = reservation_row(con)
        self.assertEqual(committed[4], 'committed')
        self.assertFalse(self.ack())

    def test_lost_reserve_reply_can_retry_same_persisted_intent(self):
        import tools.audit_record_custodian_tls as network
        original = network._process
        def lose_after_reservation(request, *args):
            result = original(request, *args)
            if request['action'] == 'reserve':
                raise OSError('private reply lost after committed reservation')
            return result
        with patch('tools.audit_record_custodian_tls._process',
                   side_effect=lose_after_reservation):
            with self.assertRaises((OSError, ValueError, ssl.SSLError)):
                self.new_issue()
        row = self.intent()
        self.assertEqual(row[1], 1)
        self.assertEqual(self.state(), (1, (1, None)))
        self.assertEqual(self.new_issue(), NONCE_B)
        self.assertEqual(self.intent()[3], row[3])

    def test_no_reservation_token_overwritten_when_remote_unavailable(self):
        original = self.transport
        def offline(*, action, checkpoint_raw,
                    expected_sequence=None, expected_receipt_sha256=None,
                    reservation_token=None):
            if action == 'reserve':
                raise OSError('network outage')
            return original(action=action, checkpoint_raw=checkpoint_raw,
                            expected_sequence=expected_sequence,
                            expected_receipt_sha256=expected_receipt_sha256,
                            reservation_token=reservation_token)
        self.transport = offline
        with self.assertRaises(OSError):
            self.new_issue()
        retained = self.intent()
        self.assertEqual(self.state()[0], 1)
        self.transport = original
        self.assertEqual(self.new_issue(), NONCE_B)
        self.assertEqual(self.intent()[3], retained[3])

    def test_invalid_ttl_is_refused_before_reserving_head(self):
        with self.assertRaises(ValueError):
            issue_reserved(
                self.verifier, self.transport, self.sign_pub,
                self.sign_pub_pin, tag=self.tag, ttl_seconds=0, now=FIXED_NOW+1)
        self.assertIsNone(self.intent())
        with sqlite3.connect(self.custody) as con:
            self.assertIsNone(reservation_row(con))
        self.assertEqual(self.state(), (1, (1, None)))

    def test_second_different_verifier_cannot_claim_reserved_head(self):
        self.new_issue()
        secondary = self.v / 'second-verifier.sqlite'
        # Restoring an older, already bootstrapped verifier state cannot
        # mint a different reservation against the occupied custody head.
        with sqlite3.connect(self.verifier) as con:
            con.execute('DELETE FROM challenges WHERE nonce=?', (NONCE_B,))
            con.execute('UPDATE receipt_gate SET pending_sequence=NULL,'
                        'pending_checkpoint_sha256=NULL')
            con.execute('DELETE FROM remote_issue_reservation')
        # This simulates an independent fork; the custodian is unchanged.
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.new_issue(NONCE_C)
        self.assertEqual(self.state(), (1, (1, None)))

    def test_unreserved_network_deposit_cannot_bypass_live_reservation(self):
        self.new_issue()
        checkpoint = self.offered()
        old = self.head()
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.run_channel(action='deposit', checkpoint=checkpoint,
                             expected_head=(old[0], old[3]))
        self.assertEqual(self.head()[0], 1)

    def test_wrong_owner_token_cannot_deposit_reserved_checkpoint(self):
        self.new_issue()
        checkpoint = self.offered()
        old = self.head()
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.run_channel(
                action='deposit-reserved', checkpoint=checkpoint,
                expected_head=(old[0], old[3]),
                reservation_token='f'*32)
        self.assertEqual(self.head()[0], 1)

    def test_deposit_after_lost_reply_is_idempotent_with_token(self):
        self.new_issue()
        import tools.audit_record_custodian_tls as network
        original = network._process
        def lose_after_deposit(request, *args):
            result = original(request, *args)
            if request['action'] == 'deposit-reserved':
                raise OSError('response lost after commit')
            return result
        with patch('tools.audit_record_custodian_tls._process',
                   side_effect=lose_after_deposit):
            with self.assertRaises((OSError, ValueError, ssl.SSLError)):
                self.ack()
        self.assertEqual(self.head()[0], 2)
        self.assertEqual(self.state()[1], (1, 2))
        self.assertTrue(self.ack())
        self.assertEqual(self.head()[0], 2)
        self.assertEqual(self.state()[1], (2, None))

    def test_next_round_uses_new_token_after_acknowledged_one(self):
        self.new_issue()
        oldtoken = self.intent()[3]
        self.assertTrue(self.ack())
        self.assertEqual(self.new_issue(NONCE_C), NONCE_C)
        self.assertEqual(self.state()[1], (2, 3))
        self.assertNotEqual(self.intent()[3], oldtoken)
        self.assertTrue(self.ack())
        self.assertEqual(self.head()[0], 3)

    def test_second_issue_during_pending_is_fail_closed(self):
        self.new_issue()
        with self.assertRaises(PendingHandoff):
            self.new_issue(NONCE_C)
        self.assertEqual(self.state()[0], 2)

    def test_pending_token_tampering_blocks_ack_without_custody_change(self):
        self.new_issue()
        with sqlite3.connect(self.verifier) as con:
            con.execute('UPDATE remote_issue_reservation SET reservation_token=?',
                        ('e'*32,))
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.ack()
        self.assertEqual(self.head()[0], 1)
        self.assertEqual(self.state()[1], (1, 2))

    def test_corrupt_intent_fails_closed_before_nonce_issue(self):
        with sqlite3.connect(self.verifier) as con:
            con.execute('CREATE TABLE remote_issue_reservation(bad INTEGER)')
        with self.assertRaises(ValueError):
            self.new_issue()
        self.assertEqual(self.state()[0], 1)

    def test_reserved_head_replay_not_valid_for_different_continuation(self):
        self.new_issue()
        reserved_token = self.intent()[3]
        self.ack()
        # Old head cannot be reused after custody advances.
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.run_channel(action='reserve',
                             expected_head=(1, '0'*64),
                             reservation_token=reserved_token)

    def test_cli_unavailable_channel_outputs_no_sensitive_data(self):
        out = io.StringIO()
        with __import__('contextlib').redirect_stdout(out):
            code = main([
                'issue', str(self.verifier), '127.0.0.1', '9', 'localhost',
                str(self.client_cert), str(self.client_key),
                str(self.ca), self.server_pin,
                str(self.sign_pub), self.sign_pub_pin,
                '--custodian-tag', self.tag])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'],
                         'invalid_private_input_or_reservation')
        self.assertNotIn(self.sign_pub_pin, out.getvalue())


if __name__ == '__main__':
    unittest.main()
