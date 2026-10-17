"""Witness-gated two-admin recovery: refuse rollback BEFORE SQL mutation.

Uses the independent Ed25519 and custodian fixture from stage 257.
No original PlayStation data or private production credentials.
"""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from tests.test_record_recovery_witness import RecoveryWitnessTests
from tools.audit_record_anchor_handoff import _read_latest
from tools.audit_record_custodian_reservation import reservation_row
from tools.audit_record_custodian_recovery import (
    approve, prepare, recover_with_witness, recover,
    RecoveryConflict, audit_history, main as recovery_cli,
)
from tools.audit_record_recovery_witness import (
    initialize, record, snapshot, sign_latest, verify,
)
from tools.audit_record_anchor_handoff import _canonical

TOKEN_NEXT = 'b'*32


class WitnessGatedRecoveryTests(unittest.TestCase):
    setUp = RecoveryWitnessTests.setUp
    reserve = RecoveryWitnessTests.reserve
    recover_once = RecoveryWitnessTests.recover_once
    record_current = RecoveryWitnessTests.record_current
    sign = RecoveryWitnessTests.sign

    def genesis(self):
        self.assertEqual(initialize(self.witness), 0)
        self.signed = self.sign()
        self.assertEqual(verify(
            self.custody, self.witness, self.signed,
            self.public, self.pin, tag=self.tag,
            require_exact=True)['verified_recoveries'], 0)

    def candidate(self):
        self.recovery_number += 1
        request_path = self.custodian_dir/(
            'guarded-request-%d.json' % self.recovery_number)
        prepare(self.custody, request_path)
        raw = request_path.read_bytes()
        signed = []
        for i, (name, key, _, _) in enumerate(self.admins):
            output = self.admin_dir / (
                'guarded-sig-%d-%d.json' % (self.recovery_number, i))
            approve(raw, name, key, output)
            signed.append(output.read_bytes())
        return raw, signed

    def guarded(self, candidate=None, signed=None, *, pin=None, witness_db=None):
        raw, signatures = self.candidate() if candidate is None else candidate
        a, b = self.admins
        return recover_with_witness(
            self.custody, raw, *signatures,
            a[0], a[2], a[3],
            b[0], b[2], b[3],
            witness_db=self.witness if witness_db is None else witness_db,
            signed_witness_raw=self.signed if signed is None else signed,
            witness_public_key=self.public,
            witness_public_pem_pin=self.pin if pin is None else pin,
            witness_tag=self.tag)

    def journal(self):
        with sqlite3.connect(self.custody) as con:
            return audit_history(con)

    def test_explicit_signed_genesis_allows_first_administrative_recovery(self):
        self.genesis()
        self.assertEqual(self.guarded(), 1)
        self.assertEqual(len(self.journal()), 1)
        with sqlite3.connect(self.custody) as con:
            self.assertIsNone(reservation_row(con))

    def test_missing_initialized_witness_blocks_first_recovery(self):
        with self.assertRaises((ValueError, RecoveryConflict)):
            self.guarded()
        self.assertEqual(self.journal(), [])
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_genesis_cannot_be_reused_before_witness_records_first_recovery(self):
        self.genesis()
        self.guarded()
        self.reserve(TOKEN_NEXT)
        with self.assertRaises(RecoveryConflict):
            self.guarded()
        self.assertEqual(len(self.journal()), 1)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_signed_updated_witness_allows_next_recovery(self):
        self.genesis()
        self.guarded()
        self.assertEqual(self.record_current(), (1, True))
        self.signed = self.sign()
        self.reserve(TOKEN_NEXT)
        self.assertEqual(self.guarded(), 2)
        self.assertEqual(len(self.journal()), 2)

    def test_rollback_of_custodian_cannot_retire_orphan_after_witness(self):
        self.genesis()
        backup = self.custodian_dir/'pre-recovery.sqlite'
        shutil.copyfile(self.custody, backup)
        backup.chmod(0o600)
        self.guarded()
        self.record_current()
        self.signed = self.sign()
        shutil.copyfile(backup, self.custody)
        self.custody.chmod(0o600)
        before = self.journal()
        with self.assertRaises(RecoveryConflict):
            self.guarded()
        self.assertEqual(self.journal(), before)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_replay_old_signed_witness_receipt_after_advance_rejected(self):
        self.genesis()
        old = self.signed
        self.guarded()
        self.record_current()
        self.signed = self.sign()
        self.reserve(TOKEN_NEXT)
        with self.assertRaises(RecoveryConflict):
            self.guarded(signed=old)
        self.assertEqual(len(self.journal()), 1)

    def test_wrong_pinned_witness_key_blocks_recovery(self):
        self.genesis()
        with self.assertRaises(RecoveryConflict):
            self.guarded(pin='f'*64)
        self.assertEqual(self.journal(), [])

    def test_fake_witness_signature_blocks_recovery(self):
        self.genesis()
        payload = json.loads(self.signed)
        payload['signature_hex'] = 'f'*128
        with self.assertRaises(RecoveryConflict):
            self.guarded(signed=_canonical(payload))
        self.assertEqual(self.journal(), [])

    def test_corrupt_local_witness_event_blocks_recovery(self):
        self.genesis()
        self.guarded()
        self.record_current()
        self.signed = self.sign()
        self.reserve(TOKEN_NEXT)
        with sqlite3.connect(self.witness) as con:
            con.execute('UPDATE recovery_witness_events SET witness_sha256=?',
                        ('f'*64,))
        with self.assertRaises((ValueError, RecoveryConflict)):
            self.guarded()
        self.assertEqual(len(self.journal()), 1)

    def test_duplicate_administrator_attempts_cannot_both_commit(self):
        self.genesis()
        proposal = self.candidate()
        def attempt(_):
            try:
                return self.guarded(candidate=proposal)
            except RecoveryConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(results.count(1), 1)
        self.assertEqual(results.count(None), 1)
        self.assertEqual(len(self.journal()), 1)

    def test_guard_failure_inside_transaction_rolls_back_recovery(self):
        self.genesis()
        with patch('tools.audit_record_recovery_witness.check_locked',
                   side_effect=ValueError('simulated concurrent witness mismatch')):
            with self.assertRaises(RecoveryConflict):
                self.guarded()
        self.assertEqual(self.journal(), [])
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_privileged_legacy_interface_still_bypasses_guard_explicitly(self):
        # Security limitation: administrative host must disable legacy path.
        self.genesis()
        self.assertEqual(self.recover_once(), 1)
        self.assertEqual(len(self.journal()), 1)

    def test_cli_guarded_recovery_and_redacted_denial(self):
        self.genesis()
        request, approvals = self.candidate()
        req = self.custodian_dir/'cli-request.json'
        req.write_bytes(request)
        req.chmod(0o600)
        a_path = self.admin_dir/'cli-a.json'
        b_path = self.admin_dir/'cli-b.json'
        a_path.write_bytes(approvals[0])
        b_path.write_bytes(approvals[1])
        a_path.chmod(0o600)
        b_path.chmod(0o600)
        signed_file = self.witness_dir/'cli-witness.json'
        signed_file.write_bytes(self.signed)
        signed_file.chmod(0o600)
        a, b = self.admins
        args = [
            'recover-guarded', str(self.custody), str(req),
            str(a_path), str(b_path),
            a[0], str(a[2]), a[3],
            b[0], str(b[2]), b[3],
            str(self.witness), str(signed_file),
            str(self.public), self.pin,
            '--witness-tag', self.tag,
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(recovery_cli(args), 0)
        self.assertTrue(json.loads(out.getvalue())['witness_guarded_recovery'])
        self.assertNotIn(self.pin, out.getvalue())
        with contextlib.redirect_stdout(out := io.StringIO()):
            self.assertEqual(recovery_cli(args), 1)
        self.assertTrue(json.loads(out.getvalue())[
            'recovery_refused_due_to_changed_state'])

    def test_genesis_cli_reinitialization_is_idempotent(self):
        self.genesis()
        self.assertEqual(initialize(self.witness), 0)
        self.guarded()
        self.assertEqual(initialize(self.witness), 0)
        self.assertEqual(self.record_current(), (1, True))
        self.assertEqual(initialize(self.witness), 1)


if __name__ == '__main__':
    unittest.main()
