"""Synthetic stage-263B durable custody write-quarantine regression tests."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import sqlite3
import unittest

from tests import test_record_witness_fence_quiescence as fixture_module
from tools.audit_record_anchor_handoff import _read_latest, deposit
from tools.audit_record_custodian_reservation import reserve
from tools.audit_record_custodian_recovery import (
    prepare as prepare_recovery, approve as approve_recovery,
    recover as recover_custodian,
)
from tools.audit_record_custodian_write_quarantine import (
    QuarantineConflict, QUARANTINE_USER_VERSION, _quarantine_row, install, main,
)
from tools.audit_record_witness_fence_quiescence import PreflightConflict

TOKEN = 'a'*32


class WriteQuarantineTests(unittest.TestCase):
    setUp = fixture_module.QuiescencePreflightTests.setUp
    request = fixture_module.QuiescencePreflightTests.request
    fence = fixture_module.QuiescencePreflightTests.fence
    stop = fixture_module.QuiescencePreflightTests.stop
    path = fixture_module.QuiescencePreflightTests.path
    outstanding = fixture_module.QuiescencePreflightTests.outstanding
    new_offer = fixture_module.QuiescencePreflightTests.new_offer
    make_offer_and_deposit = fixture_module.QuiescencePreflightTests.make_offer_and_deposit

    @classmethod
    def setUpClass(cls):
        fixture_module.QuiescencePreflightTests.setUpClass()
        for attr in ('ca', 'server_key', 'server_cert', 'server_pin',
                     'client_key', 'client_cert', 'client_pin',
                     'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, attr, getattr(fixture_module.QuiescencePreflightTests, attr))

    @classmethod
    def tearDownClass(cls):
        fixture_module.QuiescencePreflightTests.tearDownClass()

    def install(self, original, proof=None):
        signed, pub, pin = proof if proof is not None else self.stop(original)
        return install(self.custody, self.witness_db, original, signed,
                       pub, pin, supervisor_tag='independent-supervisor')

    def quarantine(self):
        with sqlite3.connect(self.custody) as con:
            return _quarantine_row(con)

    def test_not_started_reservation_seals_without_releasing_witness(self):
        original = self.request()
        self.fence(original)
        result = self.install(original)
        self.assertTrue(result['instrumented_writers_blocked'])
        self.assertFalse(result['safe_to_reconcile_negative_outcome'])
        self.assertIsNotNone(self.quarantine())
        self.assertIsNotNone(self.outstanding())
        head = _read_latest(self.custody)
        with self.assertRaises(QuarantineConflict):
            reserve(self.custody, head[0], head[3], TOKEN)
        self.assertEqual(_read_latest(self.custody)[0], head[0])

    def test_uncommitted_checkpoint_is_blocked_after_quarantine(self):
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        checkpoint = self.new_offer()
        original = self.request('deposit-reserved', offer=checkpoint)
        self.fence(original)
        result = self.install(original)
        self.assertEqual(result['negative_snapshot_classification'],
                         'checkpoint-not-committed-in-snapshot')
        with self.assertRaises(QuarantineConflict):
            deposit(self.custody, checkpoint,
                    expected_sequence=head[0],
                    expected_receipt_sha256=head[3],
                    reservation_token=TOKEN)
        with self.assertRaises(QuarantineConflict):
            reserve(self.custody, head[0], head[3], TOKEN)
        self.assertEqual(_read_latest(self.custody)[0], head[0])
        self.assertIsNotNone(self.outstanding())

    def test_legacy_unreserved_deposit_blocked(self):
        original = self.request()
        self.fence(original)
        self.install(original)
        with self.assertRaises(QuarantineConflict):
            deposit(self.custody, self.new_offer())

    def test_two_admin_custody_recovery_must_respect_quarantine(self):
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        original = self.request('deposit-reserved', offer=self.new_offer())
        self.fence(original)
        self.install(original)
        proposal_path = self.path('custodian-recovery-request-')
        prepare_recovery(self.custody, proposal_path)
        raw = proposal_path.read_bytes()
        approvals = []
        for name, key, _, _ in self.admins[:2]:
            output = self.path('custodian-recovery-approval-')
            approve_recovery(raw, name, key, output)
            approvals.append(output.read_bytes())
        a, b = self.admins[:2]
        with self.assertRaises(QuarantineConflict):
            recover_custodian(
                self.custody, raw, *approvals,
                a[0], a[2], a[3], b[0], b[2], b[3])
        self.assertEqual(self.quarantine()[0], 1)

    def test_bad_stop_claim_must_not_seal_or_release(self):
        original = self.request()
        self.fence(original)
        with self.assertRaises(ValueError):
            self.install(original, self.stop(
                original, service_restart_blocked=False))
        self.assertIsNone(self.quarantine())
        self.assertIsNotNone(self.outstanding())

    def test_applied_reservation_cannot_be_sealed_as_negative(self):
        original = self.request()
        self.fence(original)
        head = _read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        with self.assertRaises(PreflightConflict):
            self.install(original)
        self.assertIsNone(self.quarantine())

    def test_wrong_or_absent_witness_does_not_seal(self):
        original = self.request()
        with self.assertRaises(PreflightConflict):
            self.install(original)
        self.assertIsNone(self.quarantine())

    def test_tampered_quarantine_blocks_all_writers(self):
        original = self.request()
        self.fence(original)
        self.install(original)
        with sqlite3.connect(self.custody) as con:
            con.execute('UPDATE custodian_writer_quarantine '
                        'SET quarantine_event_sha256=?', ('f'*64,))
        head = _read_latest(self.custody)
        with self.assertRaises(QuarantineConflict):
            reserve(self.custody, head[0], head[3], TOKEN)
        with self.assertRaises(QuarantineConflict):
            deposit(self.custody, self.new_offer())

    def test_sealed_sqlite_header_and_row_agree(self):
        original = self.request()
        self.fence(original)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 0)
        self.install(original)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(
                con.execute('PRAGMA user_version').fetchone()[0],
                QUARANTINE_USER_VERSION)
            self.assertIsNotNone(_quarantine_row(con))

    def test_dropped_quarantine_table_still_blocks_writers(self):
        original = self.request()
        self.fence(original)
        self.install(original)
        with sqlite3.connect(self.custody) as con:
            con.execute('DROP TABLE custodian_writer_quarantine')
            self.assertEqual(
                con.execute('PRAGMA user_version').fetchone()[0],
                QUARANTINE_USER_VERSION)
        head = _read_latest(self.custody)
        with self.assertRaises(QuarantineConflict):
            reserve(self.custody, head[0], head[3], TOKEN)
        with self.assertRaises(QuarantineConflict):
            deposit(self.custody, self.new_offer())
        self.assertIsNotNone(self.outstanding())

    def test_erased_header_marker_still_blocks_writers(self):
        original = self.request()
        self.fence(original)
        self.install(original)
        with sqlite3.connect(self.custody) as con:
            con.execute('PRAGMA user_version=0')
        head = _read_latest(self.custody)
        with self.assertRaises(QuarantineConflict):
            reserve(self.custody, head[0], head[3], TOKEN)
        with self.assertRaises(QuarantineConflict):
            deposit(self.custody, self.new_offer())
        self.assertIsNotNone(self.outstanding())

    def test_nonzero_unknown_header_refuses_writes_and_install(self):
        original = self.request()
        self.fence(original)
        with sqlite3.connect(self.custody) as con:
            con.execute('PRAGMA user_version=1')
        head = _read_latest(self.custody)
        with self.assertRaises(QuarantineConflict):
            reserve(self.custody, head[0], head[3], TOKEN)
        with self.assertRaises(QuarantineConflict):
            self.install(original)
        self.assertIsNotNone(self.outstanding())

    def test_failed_install_does_not_leave_partial_header(self):
        original = self.request()
        with self.assertRaises(PreflightConflict):
            self.install(original)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertIsNone(_quarantine_row(con))

    def test_duplicate_install_refused_and_original_fence_retained(self):
        original = self.request()
        self.fence(original)
        self.install(original)
        row = self.quarantine()
        with self.assertRaises(QuarantineConflict):
            self.install(original)
        self.assertEqual(self.quarantine(), row)
        self.assertIsNotNone(self.outstanding())

    def test_write_race_cannot_both_seal_and_reserve(self):
        original = self.request()
        self.fence(original)
        head = _read_latest(self.custody)
        def apply_reserve():
            try:
                reserve(self.custody, head[0], head[3], TOKEN)
                return True
            except QuarantineConflict:
                return False
        def seal():
            try:
                self.install(original)
                return True
            except PreflightConflict:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(apply_reserve)
            b = pool.submit(seal)
            reserve_applied, seal_applied = a.result(), b.result()
        self.assertNotEqual(reserve_applied, seal_applied)
        self.assertIsNotNone(self.outstanding())

    def test_redacted_cli_reports_no_release_or_secrets(self):
        original = self.request()
        self.fence(original)
        signed, public, pin = self.stop(original)
        original_path = self.path('original-')
        stop_path = self.path('stop-')
        for target, raw in ((original_path, original),
                            (stop_path, signed)):
            target.write_bytes(raw)
            target.chmod(0o600)
        with contextlib.redirect_stdout(out := io.StringIO()):
            result = main([str(self.custody), str(self.witness_db),
                           str(original_path), str(stop_path),
                           str(public), pin,
                           '--supervisor-tag', 'independent-supervisor'])
        self.assertEqual(result, 0)
        self.assertFalse(json.loads(out.getvalue())['witness_fence_retired'])
        self.assertNotIn(TOKEN, out.getvalue())
        self.assertNotIn(pin, out.getvalue())
        self.assertIsNotNone(self.outstanding())


if __name__ == '__main__':
    unittest.main()
