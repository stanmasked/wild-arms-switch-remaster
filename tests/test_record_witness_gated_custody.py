"""Stage-259 opt-in signed witness checks on custody reserve and deposit.

All evidence is synthetic; private keys are ephemeral, generated in
protected temporary directories. Includes real loopback mutual TLS checks.
"""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import FIXED_NOW, NONCE_B
from tests.test_record_recovery_witness import RecoveryWitnessTests
from tests.test_record_custodian_tls import (
    MutualTlsCustodianTests as TLSFixture, openssl,
)
from tools.audit_record_anchor_handoff import deposit, _read_latest
from tools.audit_record_atomic_verifier import issue as legacy_issue
from tools.audit_record_custodian_reservation import (
    reserve, reservation_row, ReservationConflict,
)
from tools.audit_record_recovery_witness import (
    initialize, record, snapshot, sign_latest, authenticated_head,
    WitnessRegression,
)
from tools.audit_record_custodian_tls import main as tls_cli
from tools.audit_record_verifier_checkpoint import save_checkpoint

TOKEN_A = 'a'*32
TOKEN_B = 'b'*32
TOKEN_C = 'c'*32


class GuardedCustodianWriteTests(unittest.TestCase):
    setUp = RecoveryWitnessTests.setUp
    reserve = RecoveryWitnessTests.reserve
    recover_once = RecoveryWitnessTests.recover_once
    record_current = RecoveryWitnessTests.record_current
    sign = RecoveryWitnessTests.sign
    produce = RecoveryWitnessTests.produce

    def guarded_genesis(self):
        self.assertEqual(initialize(self.witness), 0)
        self.signed = self.sign()
        return self.head()

    def head(self):
        return authenticated_head(
            self.witness, self.signed, self.public, self.pin, tag=self.tag)

    def custody_head(self):
        row = _read_latest(self.custody)
        return row[0], row[3]

    def offer_next(self):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            legacy_issue(self.db, now=FIXED_NOW+1)
        p = self.verifier_dir/'next-for-custodian.json'
        save_checkpoint(self.db, p)
        return p.read_bytes()

    def test_genesis_allows_owned_reserved_deposit_and_next_reservation(self):
        head = self.guarded_genesis()
        offer = self.offer_next()
        seq, previous = self.custody_head()
        self.assertEqual(deposit(
            self.custody, offer, expected_sequence=seq,
            expected_receipt_sha256=previous,
            reservation_token=TOKEN_A, witness_head=head), (2, True))
        now, receipt = self.custody_head()
        self.assertTrue(reserve(
            self.custody, now, receipt, TOKEN_B, witness_head=head))
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_missing_witness_never_authorizes_mutation(self):
        # A missing witness database is a fail-closed filesystem error,
        # not a forged or synthetic signed-head value.
        with self.assertRaises((OSError, ValueError)):
            authenticated_head(
                self.witness, b'{}', self.public, self.pin, tag=self.tag)
        # No independent signed proof means the guarded caller never
        # constructs an authenticated head at all.
        self.assertEqual(self.custody_head()[0], 1)

    def test_unwitnessed_recovery_blocks_reserve_and_deposit(self):
        head = self.guarded_genesis()
        self.assertEqual(self.recover_once(), 1)
        seq, previous = self.custody_head()
        with self.assertRaises(WitnessRegression):
            reserve(self.custody, seq, previous, TOKEN_B, witness_head=head)
        with self.assertRaises(WitnessRegression):
            deposit(self.custody, self.offer_next(),
                    expected_sequence=seq,
                    expected_receipt_sha256=previous,
                    witness_head=head)
        self.assertEqual(self.custody_head()[0], 1)
        with sqlite3.connect(self.custody) as con:
            self.assertIsNone(reservation_row(con))

    def test_record_and_sign_recovery_unblocks_new_reservation_and_deposit(self):
        self.guarded_genesis()
        self.assertEqual(self.recover_once(), 1)
        self.assertEqual(self.record_current(), (1, True))
        self.signed = self.sign()
        witness = self.head()
        seq, previous = self.custody_head()
        self.assertTrue(reserve(
            self.custody, seq, previous, TOKEN_B, witness_head=witness))
        self.assertEqual(deposit(
            self.custody, self.offer_next(), expected_sequence=seq,
            expected_receipt_sha256=previous,
            reservation_token=TOKEN_B, witness_head=witness), (2, True))

    def test_rolled_back_custody_rejected_inside_reserve_and_deposit(self):
        self.guarded_genesis()
        backup = self.custodian_dir/'before-recovery.sqlite'
        shutil.copyfile(self.custody, backup)
        backup.chmod(0o600)
        self.recover_once()
        self.record_current()
        self.signed = self.sign()
        witness = self.head()
        shutil.copyfile(backup, self.custody)
        self.custody.chmod(0o600)
        seq, previous = self.custody_head()
        with self.assertRaises(WitnessRegression):
            reserve(self.custody, seq, previous, TOKEN_A, witness_head=witness)
        with self.assertRaises(WitnessRegression):
            deposit(self.custody, self.offer_next(),
                    expected_sequence=seq,
                    expected_receipt_sha256=previous,
                    reservation_token=TOKEN_A, witness_head=witness)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_stale_signed_witness_receipt_rejected_before_ledger_write(self):
        self.guarded_genesis()
        old_signature = self.signed
        self.recover_once()
        self.record_current()
        self.signed = self.sign()
        with self.assertRaises(WitnessRegression):
            authenticated_head(self.witness, old_signature,
                               self.public, self.pin, tag=self.tag)
        self.assertEqual(self.custody_head()[0], 1)

    def test_wrong_witness_public_key_pin_rejected_before_write(self):
        self.guarded_genesis()
        with self.assertRaises(ValueError):
            authenticated_head(self.witness, self.signed, self.public,
                               'f'*64, tag=self.tag)
        self.assertEqual(self.custody_head()[0], 1)

    def test_concurrent_guarded_reservers_have_only_one_winner(self):
        self.guarded_genesis()
        self.recover_once()
        self.record_current()
        self.signed = self.sign()
        witness = self.head()
        seq, previous = self.custody_head()
        def attempt(token):
            try:
                return reserve(self.custody, seq, previous, token,
                               witness_head=witness)
            except ReservationConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(attempt, (TOKEN_B, TOKEN_C)))
        self.assertEqual(result.count(True), 1)
        self.assertEqual(result.count(None), 1)

    def test_unguarded_legacy_reservation_is_still_possible(self):
        self.guarded_genesis()
        self.recover_once()
        seq, previous = self.custody_head()
        # Limitation: historical APIs are still explicitly available.
        self.assertTrue(reserve(self.custody, seq, previous, TOKEN_B))
        self.assertEqual(self.custody_head()[0], 1)


class WitnessGuardedTLSCustodianTests(unittest.TestCase):
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
        self.w = self.v/'independent-witness'
        self.w.mkdir(mode=0o700)
        self.witness = self.w/'highwater.sqlite'
        self.witness_private = self.w/'separate-signing.key'
        self.witness_public = self.w/'public.pem'
        openssl('genpkey', '-algorithm', 'ed25519',
                '-out', self.witness_private)
        openssl('pkey', '-in', self.witness_private, '-pubout',
                '-out', self.witness_public)
        self.witness_private.chmod(0o600)
        self.witness_public.chmod(0o600)
        self.witness_pin = hashlib.sha256(
            self.witness_public.read_bytes()).hexdigest()
        self.witness_tag = 'synthetic_independent_custodian_witness'
        initialize(self.witness)
        self.receipt = self.w/'genesis.json'
        sign_latest(
            self.witness, self.witness_private, self.receipt,
            tag=self.witness_tag)

    def head(self):
        return authenticated_head(
            self.witness, self.receipt.read_bytes(),
            self.witness_public, self.witness_pin, tag=self.witness_tag)

    def test_real_tls_reserve_and_deposit_require_witness_head(self):
        witness_head = self.head()
        prior = _read_latest(self.custody)
        (_, _, seq), success = self.run_channel(
            action='reserve', reservation_token=TOKEN_A,
            witness_head=witness_head)
        self.assertTrue(success)
        self.assertEqual(seq, 1)
        offer = self.new_offer()
        (checkpoint, _, seq), success = self.run_channel(
            action='deposit-reserved', checkpoint=offer,
            reservation_token=TOKEN_A, witness_head=witness_head,
            expected_head=(prior[0], prior[3]))
        self.assertTrue(success)
        self.assertEqual(checkpoint, offer)
        self.assertEqual(seq, 2)

    def test_guarded_tls_rejects_custodian_newer_unwitnessed_event(self):
        witness_head = self.head()
        # Insert a synthetically consistent recovery journal event to
        # demonstrate that guarded TLS requests fail without witness ack.
        from tools.audit_record_custodian_recovery import (
            _event, _event_hash, audit_history)
        import secrets
        with sqlite3.connect(self.custody) as con:
            audit_history(con, create=True)
            obj = {
                'expected_sequence': 1,
                'expected_receipt_sha256': _read_latest(self.custody)[3],
                'expected_token_sha256': 'e'*64,
            }
            event = _event(1, 'f'*64, obj, '0'*64)
            con.execute(
                'INSERT INTO custodian_recovery_history'
                ' (sequence,request_sha256,base_sequence,'
                'base_receipt_sha256,retired_token_sha256,'
                'previous_event_sha256,event_sha256)'
                ' VALUES(?,?,?,?,?,?,?)',
                (1, 'f'*64, 1, obj['expected_receipt_sha256'],
                 'e'*64, '0'*64, _event_hash(event)))
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.run_channel(
                action='reserve', reservation_token=TOKEN_A,
                witness_head=witness_head)
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_guarded_tls_cli_refuses_unsigned_witness_before_listener(self):
        out = io.StringIO()
        args = [
            'serve-once-witness-guarded',
            str(self.custody), str(self.sign_key),
            str(self.server_cert), str(self.server_key), str(self.ca),
            self.client_pin,
            str(self.witness), str(self.receipt),
            str(self.witness_public), 'f'*64,
            '--custodian-tag', self.tag, '--port', '38481',
            '--witness-tag', self.witness_tag,
        ]
        # The command rejects invalid pinned credentials before binding
        # a listening socket or reading a request.
        with contextlib.redirect_stdout(out):
            code = tls_cli(args)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'],
                         'invalid_private_input_or_channel')
        self.assertNotIn(self.witness_pin, out.getvalue())


if __name__ == '__main__':
    unittest.main()
