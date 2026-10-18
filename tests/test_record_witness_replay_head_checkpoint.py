"""Synthetic Stage 263M independently endorsed ledger head regressions."""
import contextlib
import hashlib
import hashlib
import io
import json
import sqlite3
import unittest

from tests import test_record_witness_run_replay_ledger as replay_fixture
from tools import audit_record_witness_replay_head_checkpoint as head
from tools import audit_record_witness_run_replay_ledger as replay
from tools.audit_record_witness_fence_reconciliation import _sign, _signed

TAG = 'private-wild-arms-ledger'
NONCE = '1'*32


class SignedReplayHeadTests(unittest.TestCase):
    setUp = replay_fixture.ReplayLedgerTests.setUp
    path = replay_fixture.ReplayLedgerTests.path
    request = replay_fixture.ReplayLedgerTests.request
    stop = replay_fixture.ReplayLedgerTests.stop
    make_cgroup = replay_fixture.ReplayLedgerTests.make_cgroup
    write_controls = replay_fixture.ReplayLedgerTests.write_controls
    snapshot = replay_fixture.ReplayLedgerTests.snapshot
    signed_stop_for = replay_fixture.ReplayLedgerTests.signed_stop_for
    new_offer = replay_fixture.ReplayLedgerTests.new_offer
    make_offer_and_deposit = replay_fixture.ReplayLedgerTests.make_offer_and_deposit
    init_capture = replay_fixture.ReplayLedgerTests.init_capture
    build = replay_fixture.ReplayLedgerTests.build
    prepare = replay_fixture.ReplayLedgerTests.prepare
    init_journal = replay_fixture.ReplayLedgerTests.init_journal
    enroll = replay_fixture.ReplayLedgerTests.enroll
    second_bundle = replay_fixture.ReplayLedgerTests.second_bundle

    @classmethod
    def setUpClass(cls):
        replay_fixture.ReplayLedgerTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(replay_fixture.ReplayLedgerTests,name))

    @classmethod
    def tearDownClass(cls):
        replay_fixture.ReplayLedgerTests.tearDownClass()

    def sign_heads(self, *, count=None, chain_head=None, prior=None,
                   nonce=NONCE, alternate_b=None, role_b='admin-b'):
        count = self.count if count is None else count
        chain_head = self.head if chain_head is None else chain_head
        prior = head.ANCHOR_GENESIS if prior is None else prior
        a = head.make_body('admin-a', count, chain_head, prior, nonce, TAG)
        b = head.make_body(role_b, count, chain_head, prior, nonce, TAG)
        first,second = self.admins[0], (
            self.admins[1] if alternate_b is None else alternate_b)
        output_a = self.path('checkpoint-admin-a-')
        output_b = self.path('checkpoint-admin-b-')
        _sign(a, head.SCHEMA, head.DOMAIN, first[1], output_a)
        _sign(b, head.SCHEMA, head.DOMAIN, second[1], output_b)
        self.admin_a = first
        self.admin_b = second
        self.signed_a = output_a.read_bytes()
        self.signed_b = output_b.read_bytes()
        self.signed_a_path = output_a
        self.signed_b_path = output_b
        self.checkpoint_pin = head.checkpoint_digest(self.signed_a, self.signed_b)
        self.prior = prior

    def verify(self, *, signed_a=None, signed_b=None, pin=None, prior=None,
               key_a=None, key_b=None, expected_tag=TAG):
        a = self.admin_a if key_a is None else key_a
        b = self.admin_b if key_b is None else key_b
        return head.verify(
            self.journal,
            self.signed_a if signed_a is None else signed_a,
            self.signed_b if signed_b is None else signed_b,
            a[2],a[3],b[2],b[3], checkpoint_tag=expected_tag,
            prior_checkpoint_pin=self.prior if prior is None else prior,
            independently_pinned_checkpoint_sha256=(
                self.checkpoint_pin if pin is None else pin))

    def test_two_admin_genesis_checkpoint_is_advisory_only(self):
        self.init_journal()
        self.sign_heads()
        result = self.verify()
        self.assertTrue(result['two_distinct_admin_ed25519_head_claims_valid'])
        self.assertTrue(result['checkpoint_matches_external_latest_pin'])
        self.assertEqual(result['checkpoint_event_count'], 0)
        for name in ('historical_replay_with_old_pins_excluded',
                     'continuous_external_head_escrow_proved',
                     'hardware_backed_rollback_prevention_proved',
                     'witness_fence_retirement_authorized',
                     'witness_fence_retired'):
            self.assertFalse(result[name])

    def test_two_admin_one_event_checkpoint(self):
        self.init_journal()
        result = self.enroll()
        self.sign_heads(count=1, chain_head=result['ledger_head_sha256'])
        audit = self.verify()
        self.assertEqual(audit['checkpoint_event_count'],1)

    def test_swapped_signer_roles_cannot_satisfy_checkpoint(self):
        self.init_journal()
        self.sign_heads()
        with self.assertRaises((head.CheckpointConflict,ValueError)):
            head.verify(
                self.journal,self.signed_b,self.signed_a,
                self.admin_a[2],self.admin_a[3],
                self.admin_b[2],self.admin_b[3],
                checkpoint_tag=TAG,prior_checkpoint_pin=self.prior,
                independently_pinned_checkpoint_sha256=self.checkpoint_pin)

    def test_same_signer_used_as_two_admins_refused(self):
        self.init_journal()
        self.sign_heads(alternate_b=self.admins[0])
        with self.assertRaises(head.CheckpointConflict):
            self.verify()

    def test_same_key_with_reformatted_pem_cannot_fake_two_signers(self):
        self.init_journal()
        self.sign_heads(alternate_b=self.admins[0])
        public = self.admin_a[2].read_text()
        lines = public.splitlines()
        self.assertGreater(len(lines[1]), 12)
        # DER material is identical; the SHA-256 of the PEM file differs.
        lines[1:2] = [lines[1][:12], lines[1][12:]]
        reformatted = self.path('same-key-alternate-pem-')
        reformatted.write_text('\n'.join(lines) + '\n')
        reformatted.chmod(0o600)
        other = ('bob', self.admin_a[1], reformatted,
                 hashlib.sha256(reformatted.read_bytes()).hexdigest())
        self.assertNotEqual(other[3], self.admin_a[3])
        with self.assertRaises(head.CheckpointConflict):
            self.verify(key_b=other)

    def test_wrong_signer_public_pin_or_signature_refused(self):
        self.init_journal()
        self.sign_heads()
        with self.assertRaises(ValueError):
            self.verify(key_a=self.admins[2])
        with self.assertRaises(ValueError):
            self.verify(signed_a=self.signed_a.replace(b'admin-a', b'admin-z'))

    def test_admin_signed_different_head_refused(self):
        self.init_journal()
        self.sign_heads()
        b = head.make_body('admin-b',0,replay.GENESIS,
                           head.ANCHOR_GENESIS,'a'*32,TAG)
        alternate = self.path('admin-b-different-nonce-')
        _sign(b,head.SCHEMA,head.DOMAIN,self.admins[1][1],alternate)
        with self.assertRaises(head.CheckpointConflict):
            self.verify(signed_b=alternate.read_bytes(),
                        pin=head.checkpoint_digest(self.signed_a,alternate.read_bytes()))

    def test_wrong_prior_anchor_refused_even_if_signed(self):
        self.init_journal()
        self.sign_heads()
        with self.assertRaises(head.CheckpointConflict):
            self.verify(prior='f'*64)

    def test_wrong_externally_retained_checkpoint_pin_refused(self):
        self.init_journal()
        self.sign_heads()
        with self.assertRaises(head.CheckpointConflict):
            self.verify(pin='f'*64)

    def test_tampered_journal_head_detected(self):
        self.init_journal()
        saved=self.enroll()
        self.sign_heads(count=1,chain_head=saved['ledger_head_sha256'])
        with sqlite3.connect(self.journal) as con:
            con.execute("UPDATE observer_replay_events SET event_sha256=?",('d'*64,))
        with self.assertRaises((head.CheckpointConflict,replay.ReplayConflict)):
            self.verify()

    def test_journal_rollback_with_later_external_checkpoint_is_refused(self):
        self.init_journal()
        first=self.enroll()
        self.sign_heads(count=1,chain_head=first['ledger_head_sha256'])
        # Deletion can make SQLite locally resemble genesis, but the
        # independently retained signed count=1 is no longer satisfied.
        with sqlite3.connect(self.journal) as con:
            con.execute('DELETE FROM observer_replay_events')
        with self.assertRaises(head.CheckpointConflict):
            self.verify()

    def test_old_signed_checkpoint_against_newer_journal_refused(self):
        self.init_journal()
        self.sign_heads()
        self.enroll()
        with self.assertRaises(head.CheckpointConflict):
            self.verify()

    def test_restored_old_db_with_restored_old_pin_remains_attack(self):
        self.init_journal()
        self.sign_heads()
        result = self.verify()
        self.assertTrue(result['signed_journal_head_matches_readonly_audit'])
        self.assertFalse(result['historical_replay_with_old_pins_excluded'])

    def test_genesis_checkpoint_cannot_claim_arbitrary_predecessor(self):
        self.init_journal()
        with self.assertRaises(head.CheckpointConflict):
            head.make_body('admin-a', 0, replay.GENESIS,
                           'f'*64, NONCE, TAG)

    def test_invalid_unsigned_template_fields_refused(self):
        for kwargs in (
            {'role':'mallory','count':0,'head':replay.GENESIS,
             'prior':head.ANCHOR_GENESIS,'nonce':NONCE,'tag':TAG},
            {'role':'admin-a','count':-1,'head':replay.GENESIS,
             'prior':head.ANCHOR_GENESIS,'nonce':NONCE,'tag':TAG},
            {'role':'admin-a','count':0,'head':'a'*64,
             'prior':head.ANCHOR_GENESIS,'nonce':NONCE,'tag':TAG},
            {'role':'admin-a','count':0,'head':replay.GENESIS,
             'prior':head.ANCHOR_GENESIS,'nonce':'not-nonce','tag':TAG},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(head.CheckpointConflict):
                    head.make_body(**kwargs)

    def test_cli_signed_checkpoint_never_exposes_secret_or_unlock(self):
        self.init_journal()
        self.sign_heads()
        args=[
            str(self.journal),str(self.signed_a_path),
            str(self.admin_a[2]),self.admin_a[3],
            str(self.signed_b_path),str(self.admin_b[2]),self.admin_b[3],
            '--checkpoint-tag',TAG,
            '--prior-checkpoint-sha256',self.prior,
            '--latest-checkpoint-sha256',self.checkpoint_pin,
        ]
        with contextlib.redirect_stdout(stream := io.StringIO()):
            code=head.main(args)
        self.assertEqual(code,0,stream.getvalue())
        result=json.loads(stream.getvalue())
        self.assertFalse(result['witness_fence_retired'])
        self.assertNotIn('signature_hex',stream.getvalue())
        self.assertNotIn('checkpoint_nonce',stream.getvalue())


if __name__ == '__main__':
    unittest.main()
