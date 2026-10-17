"""Synthetic Ed25519 custodian signing, public-key pin and gated-admission tests."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import (
    fixture, NONCE_A, NONCE_B, FIXED_NOW,
)
from tools.audit_record_atomic_verifier import issue as legacy_issue
from tools.audit_record_anchor_handoff import deposit, _canonical
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_receipt_gated_admission import (
    PendingHandoff, AnchorConflict,
)
from tools.audit_record_signed_custodian import (
    ENVELOPE_SCHEMA, MAX_SIGNED_BYTES,
    sign_latest, verify_signed, _receipt_arg, main,
)

TAG = 'independent_test_custodian'
OTHER_TAG = 'wrong_custodian'
NONCE_C = 'fedcba9876543210fedcba9876543210'


def openssl(*arguments):
    subprocess.run(['openssl', *arguments], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=10)


class SignedCustodianTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.verifier_dir = root / 'verifier'
        self.custodian_dir = root / 'custodian'
        self.verifier_dir.mkdir(mode=0o700)
        self.custodian_dir.mkdir(mode=0o700)
        self.db = self.verifier_dir / 'capture.sqlite'
        self.custody = self.custodian_dir / 'anchor.sqlite'
        self.key = self.custodian_dir / 'signer-private.pem'
        self.public = self.verifier_dir / 'signer-public.pem'
        openssl('genpkey', '-algorithm', 'ed25519', '-out', str(self.key))
        openssl('pkey', '-in', str(self.key), '-pubout', '-out', str(self.public))
        self.key.chmod(0o600)
        self.public.chmod(0o600)
        self.pin = hashlib.sha256(self.public.read_bytes()).hexdigest()
        self.sequence = 0
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            legacy_issue(self.db, now=FIXED_NOW)
        self.deposit_new()
        self.sign_new()

    def deposit_new(self):
        self.sequence += 1
        offer = self.verifier_dir / ('offer-%d.json' % self.sequence)
        save_checkpoint(self.db, offer)
        return deposit(self.custody, offer.read_bytes())

    def sign_new(self):
        target = self.custodian_dir / ('signed-%d.json' % self.sequence)
        self.assertEqual(sign_latest(
            self.custody, self.key, target, custodian_tag=TAG), self.sequence)
        self.signed_path = target
        self.signed = target.read_bytes()
        return self.signed

    def verify(self, signed=None, key=None, pin=None, tag=None):
        return verify_signed(
            self.signed if signed is None else signed,
            self.public if key is None else key,
            self.pin if pin is None else pin,
            custodian_tag=TAG if tag is None else tag)

    def mutate(self, change):
        obj = json.loads(self.signed)
        change(obj)
        return _canonical(obj)

    def bootstrap(self):
        with patch('tools.audit_record_signed_custodian._receipt_arg',
                   return_value=self.verify()):
            return main(['bootstrap', str(self.db), str(self.custody),
                         str(self.signed_path), str(self.public), self.pin,
                         '--custodian-tag', TAG])

    def test_ed25519_valid_receipt_and_secret_not_in_output(self):
        raw = self.verify()
        receipt = json.loads(raw)
        self.assertEqual(receipt['sequence'], 1)
        self.assertEqual(json.loads(self.signed)['schema'], ENVELOPE_SCHEMA)
        self.assertNotIn(NONCE_A, self.signed.decode())
        self.assertNotIn('BEGIN PRIVATE KEY', self.signed.decode())

    def test_key_pin_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pin mismatch'):
            self.verify(pin='f'*64)
        with self.assertRaises(ValueError):
            self.verify(pin='X'*64)

    def test_wrong_public_key_even_if_externally_pinned_fails_signature(self):
        another = self.verifier_dir / 'other-pub.pem'
        other_private = self.custodian_dir / 'other-private.pem'
        openssl('genpkey', '-algorithm', 'ed25519', '-out', str(other_private))
        openssl('pkey', '-in', str(other_private), '-pubout', '-out', str(another))
        another.chmod(0o600)
        self.assertNotEqual(self.pin, hashlib.sha256(another.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.verify(key=another, pin=hashlib.sha256(another.read_bytes()).hexdigest())

    def test_wrong_custodian_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'envelope'):
            self.verify(tag=OTHER_TAG)
        with self.assertRaises(ValueError):
            self.verify(tag='../invalid')

    def test_changed_receipt_content_rejected(self):
        for field, value in (
            ('sequence', 2),
            ('checkpoint_sha256', 'e'*64),
            ('previous_receipt_sha256', 'f'*64),
        ):
            with self.subTest(field=field):
                changed = self.mutate(lambda x: x['receipt'].update({field: value}))
                with self.assertRaisesRegex(ValueError, 'signature'):
                    self.verify(signed=changed)

    def test_changed_custodian_tag_rejected(self):
        changed = self.mutate(lambda x: x.update(custodian_tag=OTHER_TAG))
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.verify(signed=changed, tag=OTHER_TAG)

    def test_changed_signature_rejected(self):
        changed = self.mutate(lambda x: x.update(signature_hex='0'*128))
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.verify(signed=changed)

    def test_invalid_schema_signature_size_and_duplicates(self):
        variants = [
            b'',
            b'x' * (MAX_SIGNED_BYTES+1),
            b'{"schema":"x","schema":"y"}',
            self.mutate(lambda x: x.update(schema='different')),
            self.mutate(lambda x: x.update(signature_hex='abcd')),
            self.mutate(lambda x: x.update(signature_hex='X'*128)),
            self.mutate(lambda x: x.update(signature_hex=True)),
            self.mutate(lambda x: x.update(additional='forbidden')),
            self.mutate(lambda x: x.update(receipt=[])),
            self.mutate(lambda x: x['receipt'].update(sequence=True)),
        ]
        for item in variants:
            with self.subTest(item=item[:30]):
                with self.assertRaises(ValueError):
                    self.verify(signed=item)

    def test_signing_key_symlink_or_world_readable_refused(self):
        link = self.custodian_dir / 'signer-symlink.pem'
        link.symlink_to(self.key)
        with self.assertRaises(ValueError):
            sign_latest(self.custody, link, self.custodian_dir/'invalid.json',
                        custodian_tag=TAG)
        self.key.chmod(0o644)
        with self.assertRaises(ValueError):
            sign_latest(self.custody, self.key, self.custodian_dir/'invalid.json',
                        custodian_tag=TAG)
        self.key.chmod(0o600)

    def test_signing_recovery_after_lost_delivery(self):
        self.sequence += 1
        offer = self.verifier_dir / 'offer-2.json'
        # Ensure there is new verifier state for a second custodian round.
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            legacy_issue(self.db, now=FIXED_NOW+1)
        save_checkpoint(self.db, offer)
        deposit(self.custody, offer.read_bytes())
        with patch('tools.audit_record_signed_custodian._write_new_private',
                   side_effect=OSError('simulated transport failure')):
            with self.assertRaises(OSError):
                sign_latest(self.custody, self.key, self.custodian_dir/'lost.json',
                            custodian_tag=TAG)
        self.sign_new()
        self.assertEqual(json.loads(self.verify())['sequence'], 2)
        self.assertEqual(deposit(self.custody, offer.read_bytes()), (2, False))

    def test_private_output_cannot_overwrite_signed_receipt(self):
        with self.assertRaises(FileExistsError):
            sign_latest(self.custody, self.key, self.signed_path, custodian_tag=TAG)

    def test_unsigned_stage249_receipt_cannot_masquerade_as_signed(self):
        with self.assertRaises(ValueError):
            self.verify(signed=self.verify())

    def test_signature_verification_is_offline_not_freshness_attestation(self):
        stale = self.signed
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            legacy_issue(self.db, now=FIXED_NOW+1)
        self.deposit_new()
        self.sign_new()
        # The old receipt is still genuinely signed. High-water checking
        # belongs to the stage-249 SQLite admission protocol.
        self.assertEqual(json.loads(self.verify(signed=stale))['sequence'], 1)
        self.assertEqual(json.loads(self.verify())['sequence'], 2)

    def test_end_to_end_signed_bootstrap_issue_deposit_ack_accept(self):
        raw = self.verify()
        from tools.audit_record_receipt_gated_admission import (
            bootstrap as base_bootstrap, issue as base_issue,
            accept as base_accept, acknowledge as base_ack,
        )
        base_bootstrap(self.db, self.custody, raw)
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=NONCE_B):
            self.assertEqual(base_issue(self.db, self.custody, raw,
                                        now=FIXED_NOW+1), NONCE_B)
        with self.assertRaises(PendingHandoff):
            base_issue(self.db, self.custody, raw, now=FIXED_NOW+2)
        self.deposit_new()
        old_signed = self.signed
        self.sign_new()
        # Old signature is authentic but stale after custody advances.
        with self.assertRaises(AnchorConflict):
            base_ack(self.db, self.custody, self.verify(signed=old_signed))
        self.assertTrue(base_ack(self.db, self.custody, self.verify()))
        self.assertTrue(base_accept(self.db, self.custody, self.verify(),
                                    *fixture(NONCE_A), now=FIXED_NOW+2))
        self.deposit_new()
        self.sign_new()
        self.assertTrue(base_ack(self.db, self.custody, self.verify()))
        self.assertFalse(base_ack(self.db, self.custody, self.verify()))

    def test_cli_verify_reports_redacted_status(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['verify', str(self.signed_path), str(self.public),
                         self.pin, '--custodian-tag', TAG])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())['signature_and_public_key_pin_valid'])
        self.assertNotIn(NONCE_A, out.getvalue())
        self.assertNotIn(self.pin, out.getvalue())
        self.assertNotIn('BEGIN PRIVATE', out.getvalue())

    def test_cli_sign_and_verify_reject_forged_body(self):
        spare = self.custodian_dir / 'spare.json'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['sign', str(self.custody), str(self.key),
                         str(spare), '--custodian-tag', TAG])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())['signed_receipt_written_privately'])
        forged = self.verifier_dir / 'forged.json'
        forged.write_bytes(self.mutate(
            lambda x: x['receipt'].update(checkpoint_sha256='b'*64)))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['verify', str(forged), str(self.public),
                         self.pin, '--custodian-tag', TAG])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['error_code'], 'invalid_private_input')
        self.assertNotIn('forged', out.getvalue())

    def test_cli_bootstrap_and_signed_issue_reject_unpinned_key(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main(['bootstrap', str(self.db), str(self.custody),
                           str(self.signed_path), str(self.public), self.pin,
                           '--custodian-tag', TAG])
        self.assertEqual(status, 0)
        with patch('tools.audit_record_receipt_gated_admission.secrets.token_hex',
                   return_value=NONCE_B), patch(
                   'tools.audit_record_guarded_admission.time.time',
                   return_value=FIXED_NOW+1):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                bad = main(['issue', str(self.db), str(self.custody),
                            str(self.signed_path), str(self.public),
                            'f'*64, '--custodian-tag', TAG])
            self.assertEqual(bad, 2)
            self.assertNotIn(NONCE_B, out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                good = main(['issue', str(self.db), str(self.custody),
                             str(self.signed_path), str(self.public),
                             self.pin, '--custodian-tag', TAG])
            self.assertEqual(good, 0)
            self.assertEqual(json.loads(out.getvalue())[
                'issued_private_session_nonce'], NONCE_B)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                again = main(['issue', str(self.db), str(self.custody),
                              str(self.signed_path), str(self.public),
                              self.pin, '--custodian-tag', TAG])
            self.assertEqual(again, 1)
            self.assertTrue(json.loads(out.getvalue())['further_admission_blocked'])
            self.assertNotIn(NONCE_B, out.getvalue())

    def test_concurrent_signed_issues_only_one_wins(self):
        from tools.audit_record_receipt_gated_admission import (
            bootstrap as base_bootstrap, issue as base_issue)
        receipt = self.verify()
        base_bootstrap(self.db, self.custody, receipt)
        def attempt(_):
            try:
                return base_issue(self.db, self.custody, self.verify(),
                                  now=FIXED_NOW+1)
            except PendingHandoff:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(value is not None for value in values), 1)


if __name__ == '__main__':
    unittest.main()
