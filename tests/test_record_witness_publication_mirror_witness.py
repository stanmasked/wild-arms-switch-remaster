"""Stage 263S: synthetic two-admin signed publication mirror witness tests."""
import contextlib
import hashlib
import io
import json
import unittest

from tests import test_record_witness_publication_mirror as fixture
from tools import audit_record_witness_publication_mirror_witness as witness
from tools import audit_record_witness_publication_intake as intake
from tools.audit_record_witness_fence_reconciliation import _sign


TAG = 'private-wild-arms-publication-mirrors'
NONCE = 'a'*32


class SignedPublicationMirrorWitnessTests(unittest.TestCase):
    setUp = fixture.PublicationMirrorTests.setUp
    path = fixture.PublicationMirrorTests.path
    request = fixture.PublicationMirrorTests.request
    stop = fixture.PublicationMirrorTests.stop
    make_cgroup = fixture.PublicationMirrorTests.make_cgroup
    write_controls = fixture.PublicationMirrorTests.write_controls
    snapshot = fixture.PublicationMirrorTests.snapshot
    signed_stop_for = fixture.PublicationMirrorTests.signed_stop_for
    new_offer = fixture.PublicationMirrorTests.new_offer
    make_offer_and_deposit = fixture.PublicationMirrorTests.make_offer_and_deposit
    init_capture = fixture.PublicationMirrorTests.init_capture
    build = fixture.PublicationMirrorTests.build
    prepare = fixture.PublicationMirrorTests.prepare
    init_journal = fixture.PublicationMirrorTests.init_journal
    enroll = fixture.PublicationMirrorTests.enroll
    second_bundle = fixture.PublicationMirrorTests.second_bundle
    sign_heads = fixture.PublicationMirrorTests.sign_heads
    fresh = fixture.PublicationMirrorTests.fresh
    first_candidate = fixture.PublicationMirrorTests.first_candidate
    accept = fixture.PublicationMirrorTests.accept
    signed_round = fixture.PublicationMirrorTests.signed_round
    stage = fixture.PublicationMirrorTests.stage
    setup_intake = fixture.PublicationMirrorTests.setup_intake
    submit = fixture.PublicationMirrorTests.submit
    full_round = fixture.PublicationMirrorTests.full_round
    conflicting_receipt = fixture.PublicationMirrorTests.conflicting_receipt
    duplicate = fixture.PublicationMirrorTests.duplicate

    @classmethod
    def setUpClass(cls):
        fixture.PublicationMirrorTests.setUpClass()
        for key in ('ca','server_key','server_cert','server_pin',
                    'client_key','client_cert','client_pin',
                    'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,key,getattr(fixture.PublicationMirrorTests,key))

    @classmethod
    def tearDownClass(cls):
        fixture.PublicationMirrorTests.tearDownClass()

    def signed_mirrors(self, *, count=0, head=None, frozen=False, epoch=0,
                       prior=None, nonce=NONCE, different_b=None,
                       second_signer=None):
        self.setup_intake(0)
        if count:
            self.submit(0,'escrow-a')
            if count > 1:
                alternate=self.conflicting_receipt(0,'escrow-a',nonce='f'*32)
                self.submit(0,'escrow-a',alternate)
        self.mirror_b = self.duplicate()
        if head is None:
            head=self.i_head
        if prior is None:
            prior=witness.WITNESS_GENESIS
        self.checkpoint_prior=prior
        self.a_key=self.admins[0]
        self.b_key=self.admins[1] if second_signer is None else second_signer
        self.signed_a_path=self.path('signed-mirror-a-')
        self.signed_b_path=self.path('signed-mirror-b-')
        first=witness.make_body(witness.ROLES[0],epoch,count,head,
                                frozen,prior,nonce,TAG)
        second=witness.make_body(witness.ROLES[1],epoch,count,head,
                                 frozen,prior,nonce,TAG)
        if different_b:
            second.update(different_b)
        _sign(first,witness.SCHEMA,witness.DOMAIN,
              self.a_key[1],self.signed_a_path)
        _sign(second,witness.SCHEMA,witness.DOMAIN,
              self.b_key[1],self.signed_b_path)
        self.signed_a=self.signed_a_path.read_bytes()
        self.signed_b=self.signed_b_path.read_bytes()
        self.witness_pin=witness.witness_digest(self.signed_a,self.signed_b)

    def verify(self, *, a_raw=None,b_raw=None,pin=None,prior=None,
               a_key=None,b_key=None,a_head=None,b_head=None,
               b_path=None,scope=TAG,a_count=None,b_count=None):
        ak=self.a_key if a_key is None else a_key
        bk=self.b_key if b_key is None else b_key
        return witness.verify(
            self.intake_path,
            self.i_count if a_count is None else a_count,
            self.i_head if a_head is None else a_head,
            self.mirror_b if b_path is None else b_path,
            self.i_count if b_count is None else b_count,
            self.i_head if b_head is None else b_head,
            self.signed_a if a_raw is None else a_raw,
            ak[2],ak[3],
            self.signed_b if b_raw is None else b_raw,
            bk[2],bk[3],
            scope=scope,
            prior_witness_pin=self.checkpoint_prior if prior is None else prior,
            latest_witness_pin=self.witness_pin if pin is None else pin)

    def test_two_admin_genesis_matches_both_mirrors_but_not_unlock(self):
        self.signed_mirrors()
        report=self.verify()
        self.assertTrue(report['two_distinct_ed25519_mirror_signatures_verified'])
        self.assertTrue(report['both_mirror_chains_and_signed_heads_match'])
        self.assertFalse(report['witness_fence_retirement_authorized'])
        self.assertFalse(report['continuous_freshness_or_rollback_exclusion_proved'])

    def test_signed_nonempty_mirror_snapshot_valid(self):
        self.signed_mirrors(count=1,epoch=1)
        output=self.verify()
        self.assertEqual(output['mirror_event_count'],1)
        self.assertEqual(output['observation_epoch'],1)

    def test_signed_conflict_frozen_mirrors_preserve_fence(self):
        self.signed_mirrors(count=2,epoch=1,frozen=True)
        self.assertTrue(self.verify()['signed_conflict_freeze_state_matches'])

    def test_unsigned_snapshot_claim_cannot_be_released(self):
        with self.assertRaises(witness.MirrorWitnessConflict):
            witness.make_body(witness.ROLES[0],1,0,intake.GENESIS,
                              False,witness.WITNESS_GENESIS,'a'*32,TAG+' bad')
        with self.assertRaises(witness.MirrorWitnessConflict):
            witness.make_body(witness.ROLES[0],0,1,'f'*64,
                              False,witness.WITNESS_GENESIS,'a'*32,TAG)

    def test_conflicting_signed_event_head_rejected(self):
        self.signed_mirrors(different_b={'mirror_head_sha256':'f'*64})
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify()

    def test_conflicting_signed_conflict_state_rejected(self):
        self.signed_mirrors(different_b={'intake_frozen_by_conflict':True})
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify()

    def test_incorrect_operator_scope_or_prior_hash_refused(self):
        self.signed_mirrors()
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify(scope='another-scope')
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify(prior='f'*64)

    def test_external_signed_bundle_pin_cannot_be_replaced(self):
        self.signed_mirrors()
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify(pin='f'*64)

    def test_same_ed25519_key_cannot_play_both_roles(self):
        self.signed_mirrors(second_signer=self.admins[0])
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify()

    def test_different_pem_layout_same_material_refused(self):
        self.signed_mirrors(second_signer=self.admins[0])
        pub=self.admins[0][2].read_text().splitlines()
        pub[1:2]=[pub[1][:12],pub[1][12:]]
        path=self.path('rewrapped-ed25519-mirror-key-')
        path.write_text('\n'.join(pub)+'\n')
        path.chmod(0o600)
        alternate=(self.admins[0][0],self.admins[0][1],path,
                   hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(witness.MirrorWitnessConflict):
            self.verify(b_key=alternate)

    def test_wrong_public_key_pin_fails_signature_authenticity(self):
        self.signed_mirrors()
        with self.assertRaises(ValueError):
            self.verify(b_key=self.admins[2])

    def test_older_signed_witness_refused_after_journal_advances(self):
        self.signed_mirrors()
        self.submit(0,'escrow-a')
        with self.assertRaises((witness.MirrorWitnessConflict,
                                intake.PublicationConflict)):
            self.verify()

    def test_valid_signed_claim_does_not_overrule_divergent_mirrors(self):
        self.signed_mirrors(count=1,epoch=1)
        self.mirror_b.unlink()
        with self.assertRaises((OSError,witness.MirrorWitnessConflict)):
            self.verify()

    def test_epoch_and_nonce_schema_limits_are_enforced(self):
        for epoch,nonce in ((-1,NONCE),(True,NONCE),(0,'invalid')):
            with self.subTest(epoch=epoch,nonce=nonce):
                with self.assertRaises(witness.MirrorWitnessConflict):
                    witness.make_body(witness.ROLES[0],epoch,0,intake.GENESIS,
                                      False,witness.WITNESS_GENESIS,nonce,TAG)

    def test_replayed_old_mirror_and_old_witness_still_risk(self):
        self.signed_mirrors()
        report=self.verify()
        self.assertFalse(report['observation_epoch_is_globally_monotonic_proved'])
        self.assertFalse(report['hidden_conflicting_witnesses_excluded'])

    def test_cli_checks_private_envelopes_and_is_redacted(self):
        self.signed_mirrors()
        args=[
            str(self.intake_path),str(self.mirror_b),
            '--a-count','0','--a-head',intake.GENESIS,
            '--b-count','0','--b-head',intake.GENESIS,
            '--admin-a-signed',str(self.signed_a_path),
            '--admin-a-public',str(self.a_key[2]),
            '--admin-a-public-pin',self.a_key[3],
            '--admin-b-signed',str(self.signed_b_path),
            '--admin-b-public',str(self.b_key[2]),
            '--admin-b-public-pin',self.b_key[3],
            '--scope',TAG,
            '--prior-witness-sha256',witness.WITNESS_GENESIS,
            '--latest-witness-sha256',self.witness_pin,
        ]
        with contextlib.redirect_stdout(output := io.StringIO()):
            result=witness.main(args)
        self.assertEqual(result,0,output.getvalue())
        response=json.loads(output.getvalue())
        self.assertFalse(response['witness_fence_retired'])
        self.assertNotIn('signature_hex',output.getvalue())
        self.assertNotIn('witness_nonce',output.getvalue())


if __name__=='__main__':
    unittest.main()
