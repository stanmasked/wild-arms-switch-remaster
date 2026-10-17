"""Synthetic mutually authenticated tests for reserved capture acceptance."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import ssl
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import fixture, NONCE_A, NONCE_B, FIXED_NOW
from tests.test_record_custodian_tls import MutualTlsCustodianTests as TLSFixture
from tools.audit_record_remote_admission import bootstrap_remote
from tools.audit_record_remote_reserved_accept import (
    accept_reserved, evidence_digest, eligible, main,
)
from tools.audit_record_remote_reserved_issue import (
    _intent, _prepare, acknowledge_reserved, issue_reserved,
)
from tools.audit_record_receipt_gated_admission import PendingHandoff, AnchorConflict
from tools.audit_record_custodian_reservation import reservation_row, ReservationConflict
from tools.audit_record_anchor_handoff import deposit, _read_latest
from tools.audit_record_atomic_verifier import issue as legacy_issue
from tools.audit_record_verifier_checkpoint import save_checkpoint

OTHER = 'fedcba9876543210fedcba9876543210'


class ReservedAcceptanceTests(unittest.TestCase):
    make_offer_and_deposit = TLSFixture.make_offer_and_deposit
    new_offer = TLSFixture.new_offer
    run_channel = TLSFixture.run_channel

    @classmethod
    def setUpClass(cls):
        TLSFixture.setUpClass()
        for item in ('ca', 'server_key', 'server_cert', 'server_pin',
                     'client_key', 'client_cert', 'client_pin',
                     'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, item, getattr(TLSFixture, item))

    @classmethod
    def tearDownClass(cls):
        TLSFixture.tearDownClass()

    def setUp(self):
        TLSFixture.setUp(self)
        bootstrap_remote(self.verifier, self.channel, self.sign_pub,
                         self.sign_pub_pin, tag=self.tag)

    def channel(self, *, action, checkpoint_raw,
                expected_sequence=None, expected_receipt_sha256=None,
                reservation_token=None):
        expected = ((expected_sequence, expected_receipt_sha256)
                    if expected_sequence is not None else None)
        value, _ = self.run_channel(
            action=action, checkpoint=checkpoint_raw, expected_head=expected,
            reservation_token=reservation_token)
        return value

    def accept(self, raw=None, now=None):
        return accept_reserved(
            self.verifier, self.channel, self.sign_pub, self.sign_pub_pin,
            *(fixture(NONCE_A) if raw is None else raw), tag=self.tag,
            now=FIXED_NOW+1 if now is None else now)

    def ack(self):
        return acknowledge_reserved(
            self.verifier, self.channel, self.sign_pub,
            self.sign_pub_pin, tag=self.tag)

    def state(self):
        with sqlite3.connect(self.verifier) as c:
            return (
                c.execute('SELECT COUNT(*) FROM challenges').fetchone()[0],
                c.execute('SELECT COUNT(*) FROM accepted').fetchone()[0],
                c.execute('SELECT ack_sequence,pending_sequence FROM receipt_gate').fetchone(),
            )

    def reservation(self):
        with sqlite3.connect(self.custody) as c:
            return reservation_row(c)

    def intent(self):
        with sqlite3.connect(self.verifier) as c:
            return _intent(c)

    def test_reserved_capture_accepts_once_then_acks(self):
        self.assertTrue(self.accept())
        self.assertEqual(self.state(), (1, 1, (1, 2)))
        self.assertEqual(self.intent()[4], 'accept')
        self.assertEqual(self.intent()[5], evidence_digest(fixture(NONCE_A)))
        self.assertEqual(self.reservation()[4], 'reserved')
        self.assertTrue(self.ack())
        self.assertEqual(self.state(), (1, 1, (2, None)))
        self.assertEqual(self.reservation()[4], 'committed')
        self.assertFalse(self.ack())

    def test_capture_accepted_then_second_capture_blocked(self):
        self.assertTrue(self.accept())
        with self.assertRaises(PendingHandoff):
            self.accept()
        self.assertEqual(self.state()[1], 1)

    def test_spent_nonce_rejected_before_remote_reservation(self):
        self.accept()
        self.ack()
        self.assertFalse(self.accept())
        self.assertEqual(self.state()[1], 1)
        self.assertEqual(self.reservation()[4], 'committed')

    def test_unknown_challenge_rejected_before_reservation(self):
        self.assertFalse(self.accept(fixture(NONCE_B)))
        self.assertIsNone(self.reservation())
        self.assertIsNone(self.intent())
        self.assertEqual(self.state(), (1, 0, (1, None)))

    def test_expired_challenge_rejected_before_reservation(self):
        self.assertFalse(self.accept(now=FIXED_NOW+300))
        self.assertIsNone(self.reservation())
        self.assertIsNone(self.intent())

    def test_invalid_evidence_does_not_reserve_head(self):
        broken = list(fixture(NONCE_A))
        broken[-1] = b'{PRIVATE_MEMORY_0x800F000'
        with self.assertRaises(ValueError):
            self.accept(broken)
        self.assertIsNone(self.reservation())
        self.assertEqual(self.state()[1], 0)

    def test_missing_evidence_fields_rejected_before_network(self):
        with self.assertRaises(ValueError):
            self.accept((b'x',))
        self.assertIsNone(self.reservation())

    def test_existing_issue_intent_cannot_be_reused_for_accept(self):
        head, *_ = self.run_channel()
        receipt = _read_latest(self.custody)
        latest = (receipt[0], receipt[1], receipt[2], receipt[3], receipt[4])
        original = _prepare(self.verifier, latest)
        with self.assertRaises(AnchorConflict):
            self.accept()
        self.assertEqual(self.intent()[3], original)
        self.assertIsNone(self.reservation())

    def test_lost_reserve_reply_can_retry_same_capture(self):
        import tools.audit_record_custodian_tls as network
        call = network._process
        def drop(request, *arguments):
            response = call(request, *arguments)
            if request['action'] == 'reserve':
                raise OSError('simulated lost reply')
            return response
        with patch('tools.audit_record_custodian_tls._process', side_effect=drop):
            with self.assertRaises((OSError, ssl.SSLError, ValueError)):
                self.accept()
        original_intent = self.intent()
        self.assertEqual(self.state()[1], 0)
        self.assertTrue(self.accept())
        self.assertEqual(self.intent()[3], original_intent[3])
        self.assertEqual(self.state()[1], 1)

    def test_lost_ack_reply_retries_exact_reserved_deposit(self):
        self.assertTrue(self.accept())
        import tools.audit_record_custodian_tls as network
        call = network._process
        def drop(request, *arguments):
            response = call(request, *arguments)
            if request['action'] == 'deposit-reserved':
                raise OSError('simulated lost receipt')
            return response
        with patch('tools.audit_record_custodian_tls._process', side_effect=drop):
            with self.assertRaises((OSError, ssl.SSLError, ValueError)):
                self.ack()
        self.assertEqual(_read_latest(self.custody)[0], 2)
        self.assertEqual(self.state()[2], (1, 2))
        self.assertTrue(self.ack())
        self.assertEqual(_read_latest(self.custody)[0], 2)

    def test_legacy_deposit_blocked_even_after_reserved_commit(self):
        self.assertTrue(self.accept())
        self.assertTrue(self.ack())
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=OTHER):
            legacy_issue(self.verifier, now=FIXED_NOW+2)
        checkpoint = self.v / 'unreserved-next.json'
        save_checkpoint(self.verifier, checkpoint)
        with self.assertRaises(ReservationConflict):
            deposit(self.custody, checkpoint.read_bytes())
        self.assertEqual(_read_latest(self.custody)[0], 2)

    def test_new_issue_still_works_after_acknowledged_reserved_accept(self):
        self.assertTrue(self.accept())
        self.assertTrue(self.ack())
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=OTHER):
            nonce = issue_reserved(
                self.verifier, self.channel, self.sign_pub, self.sign_pub_pin,
                tag=self.tag, now=FIXED_NOW+2)
        self.assertEqual(nonce, OTHER)
        self.assertEqual(self.state()[2], (2, 3))
        self.assertEqual(self.intent()[4], 'issue')
        self.assertIsNone(self.intent()[5])
        self.assertTrue(self.ack())

    def test_invalid_existing_intent_schema_fails_closed(self):
        with sqlite3.connect(self.verifier) as c:
            c.execute('CREATE TABLE remote_issue_reservation(bad INTEGER)')
        with self.assertRaises(ValueError):
            self.accept()
        self.assertIsNone(self.reservation())
        self.assertEqual(self.state()[1], 0)

    def test_legacy_stage254_intent_upgrades_without_losing_token(self):
        with sqlite3.connect(self.verifier) as c:
            c.execute('CREATE TABLE remote_issue_reservation('
                      'slot INTEGER PRIMARY KEY,base_sequence INTEGER,'
                      'base_receipt_sha256 TEXT,reservation_token TEXT)')
        self.assertTrue(self.accept())
        self.assertEqual(self.intent()[4], 'accept')
        self.assertTrue(self.ack())

    def test_different_accept_evidence_cannot_reuse_same_intent(self):
        self.assertTrue(self.accept())
        receipt = _read_latest(self.custody)
        latest = (receipt[0], receipt[1], receipt[2], receipt[3], receipt[4])
        with self.assertRaises(PendingHandoff):
            _prepare(self.verifier, latest, purpose='accept',
                     evidence_sha256='e'*64)
        self.assertEqual(self.state()[1], 1)

    def test_two_concurrent_accepts_only_one_mutates_local_sqlite(self):
        def contender(_):
            try:
                return self.accept()
            except PendingHandoff:
                return False
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(contender, range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.state()[1], 1)

    def test_cli_missing_channel_reports_no_private_evidence(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = main([
                'ack', str(self.verifier), '127.0.0.1', '9', 'localhost',
                str(self.client_cert), str(self.client_key), str(self.ca),
                self.server_pin, str(self.sign_pub), self.sign_pub_pin,
                '--custodian-tag', self.tag])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'],
                         'invalid_private_input_or_custodian')
        self.assertNotIn(self.sign_pub_pin, out.getvalue())


if __name__ == '__main__':
    unittest.main()
