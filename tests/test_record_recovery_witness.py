"""Synthetic independent recovery witness, rollback, fork and signature tests."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import FIXED_NOW, NONCE_A
from tools.audit_record_atomic_verifier import issue
from tools.audit_record_anchor_handoff import deposit, _read_latest, _canonical
from tools.audit_record_custodian_reservation import reserve, reservation_row
from tools.audit_record_custodian_recovery import (
    prepare, approve, recover, _event_hash, EVENT_SCHEMA,
)
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_recovery_witness import (
    snapshot, record, sign_latest, verify, WitnessRegression, main,
    _snapshot_input, _witness_rows, MAX_SNAPSHOT_BYTES,
)

TOKEN_ONE = 'a' * 32
TOKEN_TWO = 'b' * 32


def openssl(*items):
    subprocess.run(['openssl', *map(str, items)], check=True, timeout=15,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class RecoveryWitnessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.verifier_dir = root/'verifier'
        self.custodian_dir = root/'custodian'
        self.witness_dir = root/'witness'
        self.admin_dir = root/'admins'
        for folder in (self.verifier_dir, self.custodian_dir,
                       self.witness_dir, self.admin_dir):
            folder.mkdir(mode=0o700)
        self.db = self.verifier_dir/'capture.sqlite'
        self.custody = self.custodian_dir/'anchors.sqlite'
        self.witness = self.witness_dir/'witness.sqlite'
        self.signer = self.witness_dir/'signing-private.pem'
        self.public = self.verifier_dir/'witness-public.pem'
        openssl('genpkey', '-algorithm', 'ed25519', '-out', self.signer)
        openssl('pkey', '-in', self.signer, '-pubout', '-out', self.public)
        self.signer.chmod(0o600)
        self.public.chmod(0o600)
        self.pin = hashlib.sha256(self.public.read_bytes()).hexdigest()
        self.tag = 'independent_reference_witness'
        self.admins = []
        for name in ('alice', 'bob'):
            key = self.admin_dir/(name+'.key')
            pub = self.admin_dir/(name+'.pem')
            openssl('genpkey', '-algorithm', 'ed25519', '-out', key)
            openssl('pkey', '-in', key, '-pubout', '-out', pub)
            key.chmod(0o600)
            pub.chmod(0o600)
            self.admins.append((name, key, pub,
                                hashlib.sha256(pub.read_bytes()).hexdigest()))
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            issue(self.db, now=FIXED_NOW)
        initial = self.verifier_dir/'initial.json'
        save_checkpoint(self.db, initial)
        self.assertEqual(deposit(self.custody, initial.read_bytes()), (1, True))
        self.reserve('a'*32)
        self.recovery_number = 0
        self.signed_counter = 0

    def reserve(self, token):
        anchor = _read_latest(self.custody)
        self.assertTrue(reserve(self.custody, anchor[0], anchor[3], token))

    def recover_once(self):
        self.recovery_number += 1
        p = self.custodian_dir/('request-%d.json' % self.recovery_number)
        prepare(self.custody, p)
        payload = p.read_bytes()
        signature_bytes = []
        for i, (name, key, _, _) in enumerate(self.admins):
            target = self.admin_dir / (
                'sig-%d-%d.json' % (self.recovery_number, i))
            approve(payload, name, key, target)
            signature_bytes.append(target.read_bytes())
        a, b = self.admins
        return recover(self.custody, payload, *signature_bytes,
                       a[0], a[2], a[3], b[0], b[2], b[3])

    def produce(self):
        value = snapshot(self.custody)
        return _canonical(value)

    def record_current(self):
        return record(self.witness, self.produce())

    def sign(self):
        self.signed_counter += 1
        output = self.witness_dir/('signed-%d.json' % self.signed_counter)
        sign_latest(self.witness, self.signer, output, tag=self.tag)
        return output.read_bytes()

    def check(self, signed=None, **kwargs):
        return verify(
            self.custody, self.witness,
            self.signed if signed is None else signed,
            self.public, self.pin, tag=self.tag, **kwargs)

    def first(self):
        self.assertEqual(self.recover_once(), 1)
        self.assertEqual(self.record_current(), (1, True))
        self.signed = self.sign()

    def test_sign_witness_and_detect_unchanged_record(self):
        self.first()
        report = self.check(require_exact=True)
        self.assertEqual(report['verified_recoveries'], 1)
        self.assertEqual(report['unwitnessed_recoveries'], 0)
        self.assertEqual(self.record_current(), (1, False))
        self.assertNotIn('a'*32, self.signed.decode())

    def test_sqlite_custodian_rollback_detected_against_independent_witness(self):
        old = self.custodian_dir/'before-recovery.sqlite'
        shutil.copyfile(self.custody, old)
        old.chmod(0o600)
        self.first()
        # Realistic entire-database rollback after a signed witness exists.
        shutil.copyfile(old, self.custody)
        self.custody.chmod(0o600)
        with self.assertRaises(WitnessRegression):
            self.check(require_exact=True)
        with self.assertRaises(WitnessRegression):
            self.record_current()

    def test_forged_replacement_journal_event_cannot_match_existing_witness(self):
        self.first()
        with sqlite3.connect(self.custody) as con:
            row = con.execute(
                'SELECT sequence,request_sha256,base_sequence,'
                'base_receipt_sha256,retired_token_sha256,'
                'previous_event_sha256 FROM custodian_recovery_history').fetchone()
            event = {
                'schema': EVENT_SCHEMA, 'sequence': row[0],
                'request_sha256': 'e'*64, 'base_sequence': row[2],
                'base_receipt_sha256': row[3],
                'retired_token_sha256': row[4],
                'previous_event_sha256': row[5],
            }
            con.execute(
                'UPDATE custodian_recovery_history SET request_sha256=?,'
                'event_sha256=? WHERE sequence=1',
                ('e'*64, _event_hash(event)))
        with self.assertRaises(WitnessRegression):
            self.check()
        with self.assertRaises(WitnessRegression):
            self.record_current()

    def test_rewritten_event_with_wrong_custodian_base_is_refused(self):
        self.first()
        with sqlite3.connect(self.custody) as con:
            row = con.execute(
                'SELECT sequence,request_sha256,base_sequence,'
                'base_receipt_sha256,retired_token_sha256,'
                'previous_event_sha256 FROM custodian_recovery_history').fetchone()
            forged = {
                'schema': EVENT_SCHEMA, 'sequence': row[0],
                'request_sha256': row[1], 'base_sequence': row[2],
                'base_receipt_sha256': 'e'*64,
                'retired_token_sha256': row[4],
                'previous_event_sha256': row[5],
            }
            con.execute(
                'UPDATE custodian_recovery_history SET '
                'base_receipt_sha256=?,event_sha256=? WHERE sequence=1',
                ('e'*64, _event_hash(forged)))
        with self.assertRaisesRegex(ValueError, 'not bound'):
            snapshot(self.custody)
        with self.assertRaisesRegex(ValueError, 'not bound'):
            self.check()

    def test_stale_signed_receipt_rejected_after_new_witness_event(self):
        self.first()
        old_receipt = self.signed
        self.reserve(TOKEN_TWO)
        self.assertEqual(self.recover_once(), 2)
        self.assertEqual(self.record_current(), (2, True))
        self.signed = self.sign()
        self.assertEqual(self.check()['verified_recoveries'], 2)
        with self.assertRaises(WitnessRegression):
            self.check(signed=old_receipt)

    def test_unwitnessed_new_recovery_is_reported_without_rollback_claim(self):
        self.first()
        self.reserve(TOKEN_TWO)
        self.assertEqual(self.recover_once(), 2)
        info = self.check(require_exact=False)
        self.assertEqual(info['unwitnessed_recoveries'], 1)
        with self.assertRaises(WitnessRegression):
            self.check(require_exact=True)

    def test_two_rounds_append_and_keep_exact_independent_prefix(self):
        self.first()
        self.reserve(TOKEN_TWO)
        self.recover_once()
        self.assertEqual(self.record_current(), (2, True))
        self.assertEqual(self.record_current(), (2, False))
        self.signed = self.sign()
        with sqlite3.connect(self.witness) as con:
            rows = _witness_rows(con)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], rows[0][4])
        self.assertEqual(self.check(require_exact=True)['verified_recoveries'], 2)

    def test_parallel_duplicate_witness_deposits_record_one_new_round(self):
        self.recover_once()
        exact = self.produce()
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: record(self.witness, exact), range(5)))
        self.assertEqual(sum(x[1] for x in results), 1)
        self.assertEqual({x[0] for x in results}, {1})

    def test_witness_signing_recoverable_after_output_failure(self):
        self.recover_once()
        self.record_current()
        with patch('tools.audit_record_recovery_witness._write_new_private',
                   side_effect=OSError('simulated crash during receipt delivery')):
            with self.assertRaises(OSError):
                sign_latest(self.witness, self.signer,
                            self.witness_dir/'lost.json', tag=self.tag)
        self.signed = self.sign()
        self.assertTrue(self.check(require_exact=True)[
            'current_custodian_recovery_chain_matches_witness'])

    def test_bad_public_key_pin_and_signature_rejected(self):
        self.first()
        with self.assertRaises(ValueError):
            verify(self.custody, self.witness, self.signed,
                   self.public, 'f'*64, tag=self.tag)
        envelope = json.loads(self.signed)
        envelope['signature_hex'] = '0'*128
        with self.assertRaises(ValueError):
            self.check(signed=_canonical(envelope))
        with self.assertRaises(WitnessRegression):
            verify(self.custody, self.witness, self.signed,
                   self.public, self.pin, tag='other-witness')

    def test_schema_and_snapshot_changes_rejected_without_witness_mutation(self):
        self.recover_once()
        raw = self.produce()
        bad = json.loads(raw)
        bad['recovery_events'][0]['request_sha256'] = 'e'*64
        for payload in (
                b'', b'x'*(MAX_SNAPSHOT_BYTES+1),
                b'{"schema":"one","schema":"two"}',
                _canonical(bad)):
            with self.subTest(payload=payload[:35]):
                with self.assertRaises(ValueError):
                    record(self.witness, payload)
        self.assertEqual(self.record_current(), (1, True))

    def test_tampered_stored_witness_chain_rejected(self):
        self.first()
        with sqlite3.connect(self.witness) as con:
            con.execute(
                'UPDATE recovery_witness_events SET witness_sha256=?',
                ('f'*64,))
        with self.assertRaises(ValueError):
            self.check()
        with self.assertRaises(ValueError):
            self.record_current()

    def test_wrong_witness_private_key_ownership_permissions(self):
        self.recover_once()
        self.record_current()
        self.signer.chmod(0o644)
        with self.assertRaises(ValueError):
            self.sign()
        self.signer.chmod(0o600)

    def test_cli_full_private_protocol_and_redacted_replay(self):
        self.recover_once()
        snapshot_path = self.custodian_dir/'private-0001.json'
        signed_path = self.witness_dir/'private-signed-0001.json'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['capture', str(self.custody),
                                   str(snapshot_path)]), 0)
        self.assertTrue(json.loads(out.getvalue())['private_snapshot_prepared'])
        with contextlib.redirect_stdout(out := io.StringIO()):
            self.assertEqual(main(['record', str(self.witness),
                                   str(snapshot_path)]), 0)
        self.assertTrue(json.loads(out.getvalue())['witness_history_accepted'])
        with contextlib.redirect_stdout(out := io.StringIO()):
            self.assertEqual(main(['sign', str(self.witness),
                                   str(self.signer), str(signed_path),
                                   '--witness-tag', self.tag]), 0)
        self.assertTrue(json.loads(out.getvalue())['private_witness_receipt_signed'])
        args = ['verify', str(self.custody), str(self.witness),
                str(signed_path), str(self.public), self.pin,
                '--witness-tag', self.tag, '--require-exact']
        with contextlib.redirect_stdout(out := io.StringIO()):
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(out.getvalue())['verified_recoveries'], 1)
        self.assertNotIn(self.pin, out.getvalue())
        self.assertNotIn('a'*32, out.getvalue())

    def test_cli_rejects_rollback_without_private_values(self):
        before = self.custodian_dir/'before.sqlite'
        shutil.copyfile(self.custody, before)
        before.chmod(0o600)
        self.first()
        signed_path = self.witness_dir/'file.json'
        signed_path.write_bytes(self.signed)
        signed_path.chmod(0o600)
        shutil.copyfile(before, self.custody)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main([
                'verify', str(self.custody), str(self.witness),
                str(signed_path), str(self.public), self.pin,
                '--witness-tag', self.tag])
        self.assertEqual(status, 1)
        self.assertTrue(json.loads(out.getvalue())[
            'independent_recovery_witness_mismatch'])
        self.assertNotIn(self.pin, out.getvalue())


if __name__ == '__main__':
    unittest.main()
