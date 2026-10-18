"""Synthetic Stage-263 fail-closed quiescence/negative-state preflight tests."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import unittest

from tests import test_record_witness_fence as fences
from tests import test_record_witness_fence_reconciliation as fixture
from tools.audit_record_anchor_handoff import _canonical, _read_latest, deposit
from tools.audit_record_custodian_reservation import reserve
from tools.audit_record_witness_fence import _owner
from tools.audit_record_witness_fence_reconciliation import _sign, _audit
from tools.audit_record_witness_fence_quiescence import (
    STOP_SCHEMA, STOP_DOMAIN, PreflightConflict, preflight, main,
)

TOKEN = fixture.TOKEN


class QuiescencePreflightTests(unittest.TestCase):
    # Reuse private test fixtures without inheriting their test cases.
    setUp = fixture.WitnessFenceReconciliationTests.setUp
    path = fixture.WitnessFenceReconciliationTests.path
    request = fixture.WitnessFenceReconciliationTests.request
    fence = fixture.WitnessFenceReconciliationTests.fence
    outstanding = fixture.WitnessFenceReconciliationTests.outstanding
    new_offer = fixture.WitnessFenceReconciliationTests.new_offer
    make_offer_and_deposit = fixture.WitnessFenceReconciliationTests.make_offer_and_deposit

    @classmethod
    def setUpClass(cls):
        fences.WitnessFenceTests.setUpClass()
        for field in ('ca', 'server_key', 'server_cert', 'server_pin',
                      'client_key', 'client_cert', 'client_pin',
                      'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, field, getattr(fences.WitnessFenceTests, field))

    @classmethod
    def tearDownClass(cls):
        fences.WitnessFenceTests.tearDownClass()

    def stop(self, original, **changes):
        identity, key, public, pin = self.admins[0]
        head = json.loads(original)
        body = {
            'schema': STOP_SCHEMA,
            'supervisor_tag': 'independent-supervisor',
            'custody_request_sha256': fixture._request_digest(original),
            'fence_owner_sha256': _owner(head['request_id']),
            'stop_session_nonce': '5'*32,
            'process_identity_sha256': '6'*64,
            'control_evidence_sha256': '7'*64,
            'process_tree_terminated': True,
            'service_restart_blocked': True,
            'network_ingress_blocked': True,
            'custody_writer_access_denied': True,
        }
        body.update(changes)
        target = self.path('signed-stop-')
        _sign(body, STOP_SCHEMA, STOP_DOMAIN, key, target)
        return target.read_bytes(), public, pin

    def run_preflight(self, original, stop=None):
        signed, public, pin = stop if stop is not None else self.stop(original)
        return preflight(self.witness_db, self.custody, original,
                         signed, public, pin,
                         supervisor_tag='independent-supervisor')

    def test_absent_reservation_only_preflight_not_release(self):
        original = self.request()
        self.fence(original)
        result = self.run_preflight(original)
        self.assertEqual(result['negative_snapshot_classification'],
                         'reservation-not-observed-in-snapshot')
        self.assertFalse(result['fence_retirement_authorized'])
        self.assertFalse(result['external_process_quiescence_independently_proved'])
        self.assertIsNotNone(self.outstanding())
        with sqlite3.connect(self.witness_db) as con:
            self.assertEqual(_audit(con), [])

    def test_reserved_uncommitted_deposit_only_preflight(self):
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        original = self.request('deposit-reserved', offer=self.new_offer())
        self.fence(original)
        result = self.run_preflight(original)
        self.assertEqual(result['negative_snapshot_classification'],
                         'checkpoint-not-committed-in-snapshot')
        self.assertIsNotNone(self.outstanding())

    def test_applied_reservation_never_treated_as_negative(self):
        original = self.request()
        self.fence(original)
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        with self.assertRaises(PreflightConflict):
            self.run_preflight(original)
        self.assertIsNotNone(self.outstanding())

    def test_applied_deposit_never_treated_as_negative(self):
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        checkpoint = self.new_offer()
        original = self.request('deposit-reserved', offer=checkpoint)
        self.fence(original)
        deposit(self.custody, checkpoint, expected_sequence=head[0],
                expected_receipt_sha256=head[3], reservation_token=TOKEN)
        with self.assertRaises(PreflightConflict):
            self.run_preflight(original)

    def test_wrong_or_missing_witness_fence_rejected(self):
        original = self.request()
        with self.assertRaises(PreflightConflict):
            self.run_preflight(original)
        self.fence(self.request(nonce='f'*32))
        with self.assertRaises(PreflightConflict):
            self.run_preflight(original)

    def test_signed_stop_bound_to_exact_request(self):
        original = self.request()
        self.fence(original)
        other = self.request(nonce='f'*32)
        with self.assertRaises(ValueError):
            self.run_preflight(original, self.stop(other))

    def test_untrusted_signature_and_false_shutdown_claim_rejected(self):
        original = self.request()
        self.fence(original)
        signed, public, pin = self.stop(original)
        tampered = json.loads(signed)
        tampered['signature_hex'] = '0'*128
        with self.assertRaises(ValueError):
            self.run_preflight(original, (_canonical(tampered), public, pin))
        with self.assertRaises(ValueError):
            self.run_preflight(original, self.stop(
                original, service_restart_blocked=False))
        with self.assertRaises(ValueError):
            preflight(self.witness_db, self.custody, original,
                      signed, public, 'f'*64,
                      supervisor_tag='independent-supervisor')

    def test_conflicting_reservation_blocks_negative_snapshot(self):
        original = self.request()
        self.fence(original)
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], 'b'*32)
        with self.assertRaises(PreflightConflict):
            self.run_preflight(original)

    def test_cli_redacted_and_does_not_unlock(self):
        original = self.request()
        self.fence(original)
        signed, public, pin = self.stop(original)
        request_path = self.path('request-')
        request_path.write_bytes(original)
        request_path.chmod(0o600)
        stop_path = self.path('stop-')
        stop_path.write_bytes(signed)
        stop_path.chmod(0o600)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main([str(self.witness_db), str(self.custody),
                       str(request_path), str(stop_path), str(public), pin,
                       '--supervisor-tag', 'independent-supervisor'])
        self.assertEqual(rc, 0)
        body = json.loads(out.getvalue())
        self.assertFalse(body['fence_retired'])
        self.assertNotIn(TOKEN, out.getvalue())
        self.assertNotIn(pin, out.getvalue())
        self.assertIsNotNone(self.outstanding())


if __name__ == '__main__':
    unittest.main()
