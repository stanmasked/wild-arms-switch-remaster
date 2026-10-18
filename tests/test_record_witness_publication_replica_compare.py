"""Stage 263R: two independently pinned replicas and rollback floor tests."""
import contextlib
import io
import json
import os
import sqlite3
import unittest

from tests import test_record_witness_publication_intake as prior
from tools import audit_record_witness_publication_replica_compare as compare
from tools import audit_record_witness_publication_intake as intake


class PublicationReplicaTests(unittest.TestCase):
    setUp=prior.SignedPublicationIntakeTests.setUp
    path=prior.SignedPublicationIntakeTests.path
    request=prior.SignedPublicationIntakeTests.request
    stop=prior.SignedPublicationIntakeTests.stop
    make_cgroup=prior.SignedPublicationIntakeTests.make_cgroup
    write_controls=prior.SignedPublicationIntakeTests.write_controls
    snapshot=prior.SignedPublicationIntakeTests.snapshot
    signed_stop_for=prior.SignedPublicationIntakeTests.signed_stop_for
    new_offer=prior.SignedPublicationIntakeTests.new_offer
    make_offer_and_deposit=prior.SignedPublicationIntakeTests.make_offer_and_deposit
    init_capture=prior.SignedPublicationIntakeTests.init_capture
    build=prior.SignedPublicationIntakeTests.build
    prepare=prior.SignedPublicationIntakeTests.prepare
    init_journal=prior.SignedPublicationIntakeTests.init_journal
    enroll=prior.SignedPublicationIntakeTests.enroll
    second_bundle=prior.SignedPublicationIntakeTests.second_bundle
    sign_heads=prior.SignedPublicationIntakeTests.sign_heads
    fresh=prior.SignedPublicationIntakeTests.fresh
    first_candidate=prior.SignedPublicationIntakeTests.first_candidate
    accept=prior.SignedPublicationIntakeTests.accept
    signed_round=prior.SignedPublicationIntakeTests.signed_round
    stage=prior.SignedPublicationIntakeTests.stage
    setup_intake=prior.SignedPublicationIntakeTests.setup_intake
    submit=prior.SignedPublicationIntakeTests.submit
    full_round=prior.SignedPublicationIntakeTests.full_round
    conflicting_receipt=prior.SignedPublicationIntakeTests.conflicting_receipt

    @classmethod
    def setUpClass(cls):
        prior.SignedPublicationIntakeTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(prior.SignedPublicationIntakeTests,name))

    @classmethod
    def tearDownClass(cls):
        prior.SignedPublicationIntakeTests.tearDownClass()

    def clone(self, stage=0):
        self.setup_intake(stage)
        self.replica=self.v/'independent-operator-copy.sqlite'
        with sqlite3.connect(self.intake_path) as src:
            with sqlite3.connect(self.replica) as dst:
                src.backup(dst)
        os.chmod(self.replica,0o600)
        self.b_count=self.i_count
        self.b_head=self.i_head

    def update_copy(self):
        with sqlite3.connect(self.intake_path) as src:
            with sqlite3.connect(self.replica) as dst:
                src.backup(dst)
        self.b_count=self.i_count
        self.b_head=self.i_head

    def cmp(self, *, a_count=None,a_head=None,b_count=None,b_head=None,
            floor_count=0,floor_head=intake.GENESIS,a=None,b=None):
        return compare.compare(
            self.intake_path if a is None else a,
            self.i_count if a_count is None else a_count,
            self.i_head if a_head is None else a_head,
            self.replica if b is None else b,
            self.b_count if b_count is None else b_count,
            self.b_head if b_head is None else b_head,
            floor_count=floor_count,floor_head=floor_head)

    def test_two_distinct_genesis_replicas_pass_without_release(self):
        self.clone()
        report=self.cmp()
        self.assertEqual(report['compared_event_count'],0)
        self.assertTrue(report['all_events_match_in_two_supplied_replicas'])
        for flag in ('physical_storage_independence_proved',
                     'all_hidden_forks_or_archives_discovered',
                     'rollback_if_all_pins_substituted_excluded',
                     'witness_fence_retirement_authorized',
                     'witness_fence_retired'):
            self.assertFalse(report[flag])

    def test_three_individually_published_genesis_receipts_match(self):
        self.clone()
        self.full_round(0)
        self.update_copy()
        self.assertEqual(self.cmp()['compared_event_count'],3)

    def test_six_genesis_and_successor_published_receipts_match(self):
        self.clone(1)
        self.full_round(0)
        self.full_round(1)
        self.update_copy()
        self.assertEqual(self.cmp()['compared_event_count'],6)

    def test_independently_pinned_replica_lag_detected(self):
        self.clone()
        self.submit(0,'escrow-a')
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp()

    def test_one_replica_lagging_after_full_round_detected(self):
        self.clone()
        self.full_round(0)
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp()

    def test_two_signed_conflicting_forks_from_same_genesis_detected(self):
        self.clone()
        altered=self.conflicting_receipt(0,'escrow-a',nonce='a'*32)
        self.submit(0,'escrow-a')
        published=intake.submit(
            self.replica,self.registry,altered,'escrow-a',
            self.keys['escrow-a'],self.pins['escrow-a'],
            checkpoint_tag=prior.TAG,
            expected_intake_count=0,expected_intake_head=intake.GENESIS,
            expected_registry_count=self.current_count,
            expected_registry_head=self.current_head,
            expected_registry_checkpoint=self.current_checkpoint)
        self.b_count=1
        self.b_head=published['intake_head_sha256']
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp()

    def test_same_conflict_frozen_history_is_not_positive_match(self):
        self.clone()
        self.submit(0,'escrow-a')
        altered=self.conflicting_receipt(0,'escrow-a',nonce='a'*32)
        self.submit(0,'escrow-a',altered)
        self.update_copy()
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp()

    def test_correct_independent_floor_is_verified_in_both_replicas(self):
        self.clone()
        self.full_round(0)
        historic=self.i_head
        self.update_copy()
        result=self.cmp(floor_count=3,floor_head=historic)
        self.assertTrue(result['trusted_historical_floor_present_in_both'])

    def test_historical_floor_rejects_single_replica_rollback(self):
        self.clone()
        self.full_round(0)
        historic=self.i_head
        self.update_copy()
        with sqlite3.connect(self.intake_path) as db:
            db.execute('DELETE FROM published_escrow_receipts')
        self.i_count=0
        self.i_head=intake.GENESIS
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp(floor_count=3,floor_head=historic)

    def test_historical_floor_detects_both_copies_and_pins_rolled_back(self):
        self.clone()
        self.full_round(0)
        historic=self.i_head
        self.update_copy()
        for path in (self.intake_path,self.replica):
            with sqlite3.connect(path) as db:
                db.execute('DELETE FROM published_escrow_receipts')
        self.i_count=self.b_count=0
        self.i_head=self.b_head=intake.GENESIS
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp(floor_count=3,floor_head=historic)

    def test_if_floor_also_rolled_back_previous_state_cannot_be_excluded(self):
        self.clone()
        self.full_round(0)
        self.update_copy()
        for path in (self.intake_path,self.replica):
            with sqlite3.connect(path) as db:
                db.execute('DELETE FROM published_escrow_receipts')
        self.i_count=self.b_count=0
        self.i_head=self.b_head=intake.GENESIS
        result=self.cmp()
        self.assertFalse(result['rollback_if_all_pins_substituted_excluded'])

    def test_bad_first_or_second_operator_pin_rejected(self):
        self.clone()
        for options in ({'a_head':'f'*64},{'b_head':'f'*64},
                        {'a_count':1},{'b_count':1}):
            with self.subTest(options=options):
                with self.assertRaises(intake.PublicationConflict):
                    self.cmp(**options)

    def test_forged_floor_digest_cannot_be_used(self):
        self.clone()
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp(floor_head='a'*64)
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp(floor_count=1)

    def test_same_path_is_not_two_replicas(self):
        self.clone()
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp(b=self.intake_path)

    def test_hardlinked_sqlite_alias_is_not_second_replica(self):
        self.clone()
        hardlink=self.v/'fake-independent-hardlink.sqlite'
        os.link(self.intake_path,hardlink)
        with self.assertRaises(compare.ReplicaConflict):
            self.cmp(b=hardlink)

    def test_symlinked_or_missing_replica_refused(self):
        self.clone()
        alternate=self.v/'alias-publications.sqlite'
        alternate.symlink_to(self.replica)
        with self.assertRaises((ValueError,intake.PublicationConflict)):
            self.cmp(b=alternate)
        self.replica.unlink()
        with self.assertRaises(FileNotFoundError):
            self.cmp()

    def test_corrupt_event_in_either_copy_refused(self):
        self.clone()
        self.submit(0,'escrow-a')
        self.update_copy()
        with sqlite3.connect(self.replica) as db:
            db.execute("UPDATE published_escrow_receipts SET event_sha256=?",(
                       'f'*64,))
        with self.assertRaises(intake.PublicationConflict):
            self.cmp()

    def test_schema_trigger_in_copy_refused(self):
        self.clone()
        with sqlite3.connect(self.replica) as db:
            db.execute('CREATE TRIGGER unexpected AFTER INSERT ON '
                       'published_escrow_receipts BEGIN SELECT 1; END')
        with self.assertRaises(intake.PublicationConflict):
            self.cmp()

    def test_cli_redacted_both_external_pins_and_floor(self):
        self.clone()
        with contextlib.redirect_stdout(out := io.StringIO()):
            status=compare.main([
                str(self.intake_path),str(self.replica),
                '--a-count','0','--a-head',intake.GENESIS,
                '--b-count','0','--b-head',intake.GENESIS,
                '--floor-count','0','--floor-head',intake.GENESIS])
        self.assertEqual(status,0,out.getvalue())
        report=json.loads(out.getvalue())
        self.assertFalse(report['witness_fence_retirement_authorized'])
        self.assertNotIn('round_nonce',out.getvalue())
        self.assertNotIn('signed_receipt_sha256',out.getvalue())


if __name__=='__main__':
    unittest.main()
