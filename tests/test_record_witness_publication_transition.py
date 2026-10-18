"""Stage 263V: signed mirror history transition regression tests."""
import contextlib
import hashlib
import io
import json
import shutil
import sqlite3
import unittest

from tests import test_record_witness_publication_mirror_history as fixture
from tools import audit_record_witness_publication_transition as transition
from tools import audit_record_witness_publication_mirror_history as history
from tools import audit_record_witness_publication_mirror_witness as witness
from tools import audit_record_witness_publication_intake as intake

TAG = 'private-wild-arms-publication-mirrors'


class SignedTransitionTests(unittest.TestCase):
    setUp = fixture.SignedMirrorHistoryTests.setUp
    path = fixture.SignedMirrorHistoryTests.path
    request = fixture.SignedMirrorHistoryTests.request
    stop = fixture.SignedMirrorHistoryTests.stop
    make_cgroup = fixture.SignedMirrorHistoryTests.make_cgroup
    write_controls = fixture.SignedMirrorHistoryTests.write_controls
    snapshot = fixture.SignedMirrorHistoryTests.snapshot
    signed_stop_for = fixture.SignedMirrorHistoryTests.signed_stop_for
    new_offer = fixture.SignedMirrorHistoryTests.new_offer
    make_offer_and_deposit = fixture.SignedMirrorHistoryTests.make_offer_and_deposit
    init_capture = fixture.SignedMirrorHistoryTests.init_capture
    build = fixture.SignedMirrorHistoryTests.build
    prepare = fixture.SignedMirrorHistoryTests.prepare
    init_journal = fixture.SignedMirrorHistoryTests.init_journal
    enroll = fixture.SignedMirrorHistoryTests.enroll
    second_bundle = fixture.SignedMirrorHistoryTests.second_bundle
    sign_heads = fixture.SignedMirrorHistoryTests.sign_heads
    fresh = fixture.SignedMirrorHistoryTests.fresh
    first_candidate = fixture.SignedMirrorHistoryTests.first_candidate
    accept = fixture.SignedMirrorHistoryTests.accept
    signed_round = fixture.SignedMirrorHistoryTests.signed_round
    stage = fixture.SignedMirrorHistoryTests.stage
    setup_intake = fixture.SignedMirrorHistoryTests.setup_intake
    submit = fixture.SignedMirrorHistoryTests.submit
    full_round = fixture.SignedMirrorHistoryTests.full_round
    conflicting_receipt = fixture.SignedMirrorHistoryTests.conflicting_receipt
    duplicate = fixture.SignedMirrorHistoryTests.duplicate
    sign_epoch = fixture.SignedMirrorHistoryTests.sign_epoch
    build_history = fixture.SignedMirrorHistoryTests.build_history

    @classmethod
    def setUpClass(cls):
        fixture.SignedMirrorHistoryTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(fixture.SignedMirrorHistoryTests,name))

    @classmethod
    def tearDownClass(cls):
        fixture.SignedMirrorHistoryTests.tearDownClass()

    def transition_fixture(self, events=1):
        self.build_history(0)
        self.old_a=self.v/'earlier-operator-a.sqlite'
        self.old_b=self.v/'earlier-operator-b.sqlite'
        for origin,target in ((self.intake_path,self.old_a),
                              (self.mirror_b,self.old_b)):
            shutil.copyfile(origin,target)
            target.chmod(0o600)
        self.old_archive=self.archive
        self.old_pin=self.archive_pin
        self.old_tip=self.latest
        self.old_count=0
        self.old_head=intake.GENESIS
        for epoch in range(1,events+1):
            self.submit(0,('escrow-a','escrow-b','escrow-c')[epoch-1])
            shutil.copyfile(self.intake_path,self.mirror_b)
            predecessor=self.latest
            signed=self.sign_epoch(epoch,self.i_head,False,predecessor)
            self.claims.append(signed)
            self.latest=witness.witness_digest(
                signed[witness.ROLES[0]],signed[witness.ROLES[1]])
        self.archive=history.pack(self.claims)
        self.archive_pin=hashlib.sha256(self.archive).hexdigest()

    def check(self, *, old_a=None,old_b=None,old_count=None,old_head=None,
              old_archive=None,old_pin=None,old_tip=None,
              new_a=None,new_b=None,new_count=None,new_head=None,
              new_archive=None,new_pin=None,new_tip=None):
        return transition.verify(
            self.old_a if old_a is None else old_a,
            self.old_b if old_b is None else old_b,
            self.old_count if old_count is None else old_count,
            self.old_head if old_head is None else old_head,
            self.old_archive if old_archive is None else old_archive,
            self.old_pin if old_pin is None else old_pin,
            self.old_tip if old_tip is None else old_tip,
            self.intake_path if new_a is None else new_a,
            self.mirror_b if new_b is None else new_b,
            self.i_count if new_count is None else new_count,
            self.i_head if new_head is None else new_head,
            self.archive if new_archive is None else new_archive,
            self.archive_pin if new_pin is None else new_pin,
            self.latest if new_tip is None else new_tip,
            self.admins[0][2],self.admins[0][3],
            self.admins[1][2],self.admins[1][3],scope=TAG)

    def test_one_signed_new_epoch_extends_old_history(self):
        self.transition_fixture(1)
        report=self.check()
        self.assertEqual(report['newly_added_events'],1)
        self.assertTrue(report['exact_published_event_prefix_preserved'])
        self.assertTrue(report['exact_signed_witness_epoch_prefix_preserved'])
        self.assertFalse(report['witness_fence_retirement_authorized'])

    def test_three_new_epochs_extend_old_history(self):
        self.transition_fixture(3)
        report=self.check()
        self.assertEqual(report['newly_added_events'],3)
        self.assertEqual(report['new_event_count'],3)

    def test_equal_counts_never_prove_forward_progress(self):
        self.transition_fixture(1)
        with self.assertRaises(transition.TransitionConflict):
            self.check(old_count=1)

    def test_reversed_or_decreased_order_refused(self):
        self.transition_fixture(1)
        with self.assertRaises(transition.TransitionConflict):
            self.check(old_count=2)

    def test_same_sqlite_inode_does_not_prove_two_time_snapshots(self):
        self.transition_fixture(1)
        with self.assertRaises(transition.TransitionConflict):
            self.check(old_a=self.intake_path)
        with self.assertRaises(transition.TransitionConflict):
            self.check(new_b=self.old_b)

    def test_changed_old_operator_pin_refused(self):
        self.transition_fixture(1)
        with self.assertRaises(ValueError):
            self.check(old_head='f'*64)

    def test_changed_new_operator_pin_refused(self):
        self.transition_fixture(1)
        with self.assertRaises(ValueError):
            self.check(new_head='f'*64)

    def test_different_valid_signed_genesis_cannot_replace_ancestor(self):
        self.transition_fixture(1)
        rewritten=[]
        prior=witness.WITNESS_GENESIS
        for epoch in range(2):
            event=(intake.GENESIS if epoch==0 else self.i_head)
            item=self.sign_epoch(epoch,event,False,prior,
                                 nonce=format(200+epoch,'032x'))
            rewritten.append(item)
            prior=witness.witness_digest(
                item[witness.ROLES[0]],item[witness.ROLES[1]])
        alternate=history.pack(rewritten)
        # Both histories authenticate the same actual journal events;
        # the old signed genesis was nevertheless replaced.
        with self.assertRaises(transition.TransitionConflict):
            self.check(new_archive=alternate,
                       new_pin=hashlib.sha256(alternate).hexdigest(),
                       new_tip=prior)

    def test_new_archive_missing_intermediate_epoch_refused(self):
        self.transition_fixture(2)
        shorter=history.pack([self.claims[0],self.claims[2]])
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(new_archive=shorter,
                       new_pin=hashlib.sha256(shorter).hexdigest())

    def test_wrong_old_or_new_signer_digest_rejected(self):
        self.transition_fixture(1)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(old_tip='f'*64)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(new_tip='f'*64)

    def test_tampered_historical_sqlite_chain_refused(self):
        self.transition_fixture(1)
        with sqlite3.connect(self.old_a) as con:
            con.execute('PRAGMA user_version=0')
        with self.assertRaises(ValueError):
            self.check()

    def test_same_old_pins_allow_forged_global_freshness_claim_never(self):
        self.transition_fixture(1)
        report=self.check()
        self.assertFalse(report['independently_trusted_latest_head_proved'])
        self.assertFalse(report['old_plus_new_pins_cannot_both_be_replayed_proved'])

    def test_cli_redacted_and_no_witness_release(self):
        self.transition_fixture(1)
        earlier=self.path('earlier-signed-history-')
        later=self.path('later-signed-history-')
        for path,raw in ((earlier,self.old_archive),(later,self.archive)):
            path.write_bytes(raw)
            path.chmod(0o600)
        args=[
            str(self.old_a),str(self.old_b),str(earlier),
            str(self.intake_path),str(self.mirror_b),str(later),
            '--old-count','0','--old-head',self.old_head,
            '--old-history-sha256',self.old_pin,
            '--old-latest-witness-sha256',self.old_tip,
            '--new-count','1','--new-head',self.i_head,
            '--new-history-sha256',self.archive_pin,
            '--new-latest-witness-sha256',self.latest,
            '--admin-a-public',str(self.admins[0][2]),
            '--admin-a-public-pin',self.admins[0][3],
            '--admin-b-public',str(self.admins[1][2]),
            '--admin-b-public-pin',self.admins[1][3],
            '--scope',TAG,
        ]
        with contextlib.redirect_stdout(out := io.StringIO()):
            status=transition.main(args)
        self.assertEqual(status,0,out.getvalue())
        result=json.loads(out.getvalue())
        self.assertFalse(result['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__=='__main__':
    unittest.main()
