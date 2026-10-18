"""Stage 263W: challenged latest-head Ed25519 notary regression tests."""
import contextlib
import hashlib
import io
import json
import unittest

from tests import test_record_witness_publication_transition as fixture
from tools import audit_record_witness_publication_latest_head as latest
from tools import audit_record_witness_publication_mirror_witness as witness
from tools.audit_record_witness_fence_reconciliation import _sign

TAG = 'private-wild-arms-publication-mirrors'
CHALLENGE = '7'*32


class LatestHeadNotaryTests(unittest.TestCase):
    setUp=fixture.SignedTransitionTests.setUp
    path=fixture.SignedTransitionTests.path
    request=fixture.SignedTransitionTests.request
    stop=fixture.SignedTransitionTests.stop
    make_cgroup=fixture.SignedTransitionTests.make_cgroup
    write_controls=fixture.SignedTransitionTests.write_controls
    snapshot=fixture.SignedTransitionTests.snapshot
    signed_stop_for=fixture.SignedTransitionTests.signed_stop_for
    new_offer=fixture.SignedTransitionTests.new_offer
    make_offer_and_deposit=fixture.SignedTransitionTests.make_offer_and_deposit
    init_capture=fixture.SignedTransitionTests.init_capture
    build=fixture.SignedTransitionTests.build
    prepare=fixture.SignedTransitionTests.prepare
    init_journal=fixture.SignedTransitionTests.init_journal
    enroll=fixture.SignedTransitionTests.enroll
    second_bundle=fixture.SignedTransitionTests.second_bundle
    sign_heads=fixture.SignedTransitionTests.sign_heads
    fresh=fixture.SignedTransitionTests.fresh
    first_candidate=fixture.SignedTransitionTests.first_candidate
    accept=fixture.SignedTransitionTests.accept
    signed_round=fixture.SignedTransitionTests.signed_round
    stage=fixture.SignedTransitionTests.stage
    setup_intake=fixture.SignedTransitionTests.setup_intake
    submit=fixture.SignedTransitionTests.submit
    full_round=fixture.SignedTransitionTests.full_round
    conflicting_receipt=fixture.SignedTransitionTests.conflicting_receipt
    duplicate=fixture.SignedTransitionTests.duplicate
    sign_epoch=fixture.SignedTransitionTests.sign_epoch
    build_history=fixture.SignedTransitionTests.build_history
    transition_fixture=fixture.SignedTransitionTests.transition_fixture

    @classmethod
    def setUpClass(cls):
        fixture.SignedTransitionTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(fixture.SignedTransitionTests,name))

    @classmethod
    def tearDownClass(cls):
        fixture.SignedTransitionTests.tearDownClass()

    def endorse(self, *, change_b=None, challenge=CHALLENGE,
                second_key=None):
        self.transition_fixture(1)
        self.notary_keys=(self.admins[1],
                          self.admins[2] if second_key is None else second_key)
        paths=[]
        signed=[]
        for index,role in enumerate(latest.ROLES):
            body=latest.make_body(
                role,TAG,challenge,
                self.old_count,self.old_head,self.old_pin,self.old_tip,
                self.i_count,self.i_head,self.archive_pin,self.latest)
            if index == 1 and change_b:
                body.update(change_b)
            file=self.path('latest-notary-'+role+'-')
            _sign(body,latest.SCHEMA,latest.DOMAIN,
                  self.notary_keys[index][1],file)
            paths.append(file)
            signed.append(file.read_bytes())
        self.notary_paths=paths
        self.signed_notaries=signed
        self.external_pin=latest.bundle_digest(*signed)
        self.challenge=challenge

    def check(self, *, signed_a=None,signed_b=None,notary_a=None,
              notary_b=None,external_pin=None,challenge=None,
              current_count=None,current_head=None,
              current_history=None,current_tip=None,
              new_count=None,new_head=None,new_archive=None,
              new_history_pin=None,new_tip=None,
              old_count=None,old_head=None,old_archive=None,
              old_history_pin=None,old_tip=None):
        keys=(self.notary_keys[0] if notary_a is None else notary_a,
              self.notary_keys[1] if notary_b is None else notary_b)
        return latest.verify(
            self.old_a,self.old_b,
            self.old_count if old_count is None else old_count,
            self.old_head if old_head is None else old_head,
            self.old_archive if old_archive is None else old_archive,
            self.old_pin if old_history_pin is None else old_history_pin,
            self.old_tip if old_tip is None else old_tip,
            self.intake_path,self.mirror_b,
            self.i_count if new_count is None else new_count,
            self.i_head if new_head is None else new_head,
            self.archive if new_archive is None else new_archive,
            self.archive_pin if new_history_pin is None else new_history_pin,
            self.latest if new_tip is None else new_tip,
            self.admins[0][2],self.admins[0][3],
            self.admins[1][2],self.admins[1][3],
            self.signed_notaries[0] if signed_a is None else signed_a,
            keys[0][2],keys[0][3],
            self.signed_notaries[1] if signed_b is None else signed_b,
            keys[1][2],keys[1][3],
            scope=TAG,
            external_challenge=self.challenge if challenge is None else challenge,
            external_latest_count=(
                self.i_count if current_count is None else current_count),
            external_latest_head=self.i_head if current_head is None else current_head,
            external_latest_history=(
                self.archive_pin if current_history is None else current_history),
            external_latest_witness=(
                self.latest if current_tip is None else current_tip),
            external_notary_bundle=(
                self.external_pin if external_pin is None else external_pin))

    def test_two_signed_notaries_bind_current_head_and_challenge(self):
        self.endorse()
        result=self.check()
        self.assertTrue(result['external_challenge_authenticated_by_two_notaries'])
        self.assertTrue(result['full_signed_prefix_transition_verified'])
        self.assertFalse(result['witness_fence_retired'])
        self.assertFalse(result['actual_external_challenge_freshness_proved'])

    def test_stale_external_count_refused(self):
        self.endorse()
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(current_count=0)

    def test_stale_external_current_head_refused(self):
        self.endorse()
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(current_head='f'*64)

    def test_old_externally_pinned_history_refused(self):
        self.endorse()
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(current_history=self.old_pin)

    def test_old_externally_pinned_witness_refused(self):
        self.endorse()
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(current_tip=self.old_tip)

    def test_changed_out_of_band_challenge_refused(self):
        self.endorse()
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(challenge='a'*32)

    def test_notary_a_and_b_conflicting_signed_current_head_refused(self):
        self.endorse(change_b={'new_head_sha256':'f'*64})
        with self.assertRaises(latest.LatestHeadConflict):
            self.check()

    def test_unsafe_release_assertion_is_never_authorized(self):
        self.endorse(change_b={'witness_fence_retirement_authorized':True})
        with self.assertRaises(latest.LatestHeadConflict):
            self.check()

    def test_different_signed_notary_bundle_external_pin_refused(self):
        self.endorse()
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(external_pin='f'*64)

    def test_notaries_cannot_use_one_public_key_twice(self):
        self.endorse(second_key=self.admins[1])
        with self.assertRaises(latest.LatestHeadConflict):
            self.check()

    def test_swapped_signatures_cannot_change_notary_role(self):
        self.endorse()
        with self.assertRaises(ValueError):
            self.check(signed_a=self.signed_notaries[1])

    def test_altered_witness_archive_does_not_pass_valid_notaries(self):
        self.endorse()
        corrupted=bytearray(self.archive)
        corrupted[-2] ^= 1
        with self.assertRaises(ValueError):
            self.check(new_archive=bytes(corrupted),
                       new_history_pin=hashlib.sha256(corrupted).hexdigest(),
                       current_history=hashlib.sha256(corrupted).hexdigest())

    def test_replay_old_certificate_with_new_challenge_refused(self):
        self.endorse()
        # Notaries signed a previous verifier challenge; even when the
        # operator re-pins their envelope file SHA, it is stale here.
        with self.assertRaises(latest.LatestHeadConflict):
            self.check(challenge='b'*32,
                       external_pin=latest.bundle_digest(*self.signed_notaries))

    def test_invalid_unsigned_statement_bounds(self):
        self.endorse()
        for old,new,nonce in ((1,1,CHALLENGE),
                               (0,1,'bad'),
                               (0,True,CHALLENGE)):
            with self.subTest(old=old,new=new,nonce=nonce):
                with self.assertRaises(latest.LatestHeadConflict):
                    latest.make_body('notary-a',TAG,nonce,old,self.old_head,
                                     self.old_pin,self.old_tip,new,self.i_head,
                                     self.archive_pin,self.latest)

    def test_old_complete_pins_can_still_replay_when_external_pin_compromised(self):
        self.endorse()
        result=self.check()
        self.assertFalse(result['old_pins_plus_old_challenge_replay_excluded'])
        self.assertFalse(result['trusted_current_external_pin_storage_proved'])

    def test_cli_redaction_and_no_release(self):
        self.endorse()
        oldfile=self.path('notary-old-history-')
        newfile=self.path('notary-new-history-')
        for p,raw in ((oldfile,self.old_archive),(newfile,self.archive)):
            p.write_bytes(raw)
            p.chmod(0o600)
        args=[
            str(self.old_a),str(self.old_b),str(oldfile),
            str(self.intake_path),str(self.mirror_b),str(newfile),
            '--old-count','0','--old-head',self.old_head,
            '--old-history-sha256',self.old_pin,
            '--old-latest-witness-sha256',self.old_tip,
            '--new-count','1','--new-head',self.i_head,
            '--new-history-sha256',self.archive_pin,
            '--new-latest-witness-sha256',self.latest,
            '--witness-admin-a-public',str(self.admins[0][2]),
            '--witness-admin-a-public-pin',self.admins[0][3],
            '--witness-admin-b-public',str(self.admins[1][2]),
            '--witness-admin-b-public-pin',self.admins[1][3],
            '--notary-a-signed',str(self.notary_paths[0]),
            '--notary-a-public',str(self.notary_keys[0][2]),
            '--notary-a-public-pin',self.notary_keys[0][3],
            '--notary-b-signed',str(self.notary_paths[1]),
            '--notary-b-public',str(self.notary_keys[1][2]),
            '--notary-b-public-pin',self.notary_keys[1][3],
            '--scope',TAG,
            '--external-challenge-nonce',self.challenge,
            '--external-latest-count','1',
            '--external-latest-head',self.i_head,
            '--external-latest-history-sha256',self.archive_pin,
            '--external-latest-witness-sha256',self.latest,
            '--external-notary-bundle-sha256',self.external_pin,
        ]
        with contextlib.redirect_stdout(s := io.StringIO()):
            code=latest.main(args)
        self.assertEqual(code,0,s.getvalue())
        report=json.loads(s.getvalue())
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn('signature_hex',s.getvalue())
        self.assertNotIn('challenge_nonce',s.getvalue())


if __name__=='__main__':
    unittest.main()
