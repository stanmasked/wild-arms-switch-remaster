"""Stage 263N: atomic accepted checkpoint registry/fork regression tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
import unittest

from tests import test_record_witness_replay_head_checkpoint as head_fixture
from tools import audit_record_witness_checkpoint_registry as registry
from tools import audit_record_witness_replay_head_checkpoint as checkpoint
from tools import audit_record_witness_run_replay_ledger as replay


class AcceptedCheckpointRegistryTests(unittest.TestCase):
    setUp = head_fixture.SignedReplayHeadTests.setUp
    path = head_fixture.SignedReplayHeadTests.path
    request = head_fixture.SignedReplayHeadTests.request
    stop = head_fixture.SignedReplayHeadTests.stop
    make_cgroup = head_fixture.SignedReplayHeadTests.make_cgroup
    write_controls = head_fixture.SignedReplayHeadTests.write_controls
    snapshot = head_fixture.SignedReplayHeadTests.snapshot
    signed_stop_for = head_fixture.SignedReplayHeadTests.signed_stop_for
    new_offer = head_fixture.SignedReplayHeadTests.new_offer
    make_offer_and_deposit = head_fixture.SignedReplayHeadTests.make_offer_and_deposit
    init_capture = head_fixture.SignedReplayHeadTests.init_capture
    build = head_fixture.SignedReplayHeadTests.build
    prepare = head_fixture.SignedReplayHeadTests.prepare
    init_journal = head_fixture.SignedReplayHeadTests.init_journal
    enroll = head_fixture.SignedReplayHeadTests.enroll
    second_bundle = head_fixture.SignedReplayHeadTests.second_bundle
    sign_heads = head_fixture.SignedReplayHeadTests.sign_heads

    @classmethod
    def setUpClass(cls):
        head_fixture.SignedReplayHeadTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(head_fixture.SignedReplayHeadTests,name))

    @classmethod
    def tearDownClass(cls):
        head_fixture.SignedReplayHeadTests.tearDownClass()

    def fresh(self):
        self.init_journal()
        self.registry = self.v/'independent-accepted-heads.sqlite'
        info = registry.initialize(self.registry)
        self.assertEqual(info['registry_event_count'],0)
        self.assertEqual(info['registry_head_sha256'],registry.GENESIS)
        self.assertEqual(info['latest_checkpoint_sha256'],
                         checkpoint.ANCHOR_GENESIS)
        self.rcount = 0
        self.rhead = registry.GENESIS
        self.rcheckpoint = checkpoint.ANCHOR_GENESIS

    def first_candidate(self, *, nonce='1'*32):
        enrolled = self.enroll()
        self.replay_first = enrolled
        self.sign_heads(count=1,chain_head=enrolled['ledger_head_sha256'],
                        prior=checkpoint.ANCHOR_GENESIS,nonce=nonce)

    def accept(self, *, signed_a=None, signed_b=None, candidate=None,
               prior=None, count=None, head=None, latest=None,
               admin_a=None, admin_b=None, scope=head_fixture.TAG):
        a = self.admin_a if admin_a is None else admin_a
        b = self.admin_b if admin_b is None else admin_b
        return registry.accept(
            self.registry,self.journal,
            self.signed_a if signed_a is None else signed_a,
            self.signed_b if signed_b is None else signed_b,
            a[2],a[3],b[2],b[3],
            checkpoint_tag=scope,
            prior_checkpoint_pin=self.prior if prior is None else prior,
            candidate_checkpoint_pin=(
                self.checkpoint_pin if candidate is None else candidate),
            expected_registry_count=self.rcount if count is None else count,
            expected_registry_head=self.rhead if head is None else head,
            expected_latest_checkpoint_pin=(
                self.rcheckpoint if latest is None else latest))

    def test_initialize_and_readonly_genesis_is_advisory(self):
        self.fresh()
        result=registry.inspect(
            self.registry,0,registry.GENESIS,checkpoint.ANCHOR_GENESIS)
        self.assertFalse(result['external_latest_registry_escrow_proved'])
        self.assertFalse(result['two_admin_head_accepted_once'])
        self.assertFalse(result['witness_fence_retired'])

    def test_first_dual_signature_checkpoint_accepted_atomically(self):
        self.fresh()
        self.first_candidate()
        result=self.accept()
        self.assertEqual(result['registry_event_count'],1)
        self.assertTrue(result['two_admin_head_accepted_once'])
        self.assertEqual(result['latest_checkpoint_sha256'],
                         self.checkpoint_pin)
        self.assertFalse(result['witness_fence_retirement_authorized'])
        again=registry.inspect(
            self.registry,1,result['registry_head_sha256'],self.checkpoint_pin)
        self.assertEqual(again['registry_event_count'],1)

    def test_same_signed_checkpoint_cannot_be_published_twice(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        with self.assertRaises(registry.RegistryConflict):
            self.accept(count=1,head=first['registry_head_sha256'],
                        latest=first['latest_checkpoint_sha256'])

    def test_stale_registry_head_and_tip_fail_closed(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(
                self.registry,0,registry.GENESIS,checkpoint.ANCHOR_GENESIS)
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(
                self.registry,1,first['registry_head_sha256'],'f'*64)
        with self.assertRaises(registry.RegistryConflict):
            self.accept()

    def test_new_second_checkpoint_extends_only_exact_previous_tip(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        raw,pin,reports,signed=self.second_bundle()
        second_replay=self.enroll(
            composite_raw=raw,composite_pin=pin,reports=reports,
            signed=signed,expected_count=1,
            expected_head=self.replay_first['ledger_head_sha256'])
        self.sign_heads(
            count=2,chain_head=second_replay['ledger_head_sha256'],
            prior=first['latest_checkpoint_sha256'],nonce='2'*32)
        accepted=self.accept(
            count=1,head=first['registry_head_sha256'],
            latest=first['latest_checkpoint_sha256'])
        self.assertEqual(accepted['registry_event_count'],2)
        self.assertNotEqual(accepted['registry_head_sha256'],
                            first['registry_head_sha256'])

    def test_wrong_predecessor_even_with_valid_two_signatures_refused(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        # Signatures are valid, but new claim points to the original genesis
        # instead of the already accepted first checkpoint.
        self.sign_heads(count=1,chain_head=self.replay_first['ledger_head_sha256'],
                        prior=checkpoint.ANCHOR_GENESIS,nonce='2'*32)
        with self.assertRaises(registry.RegistryConflict):
            self.accept(count=1,head=first['registry_head_sha256'],
                        latest=first['latest_checkpoint_sha256'])

    def test_competing_valid_heads_same_parent_only_one_accepted(self):
        self.fresh()
        self.first_candidate(nonce='1'*32)
        first=(self.signed_a,self.signed_b,self.checkpoint_pin)
        self.sign_heads(count=1,chain_head=self.replay_first['ledger_head_sha256'],
                        prior=checkpoint.ANCHOR_GENESIS,nonce='2'*32)
        second=(self.signed_a,self.signed_b,self.checkpoint_pin)
        def attempt(candidate):
            try:
                return ('accepted',self.accept(
                    signed_a=candidate[0],signed_b=candidate[1],
                    candidate=candidate[2]))
            except registry.RegistryConflict:
                return ('rejected',None)
        with ThreadPoolExecutor(max_workers=2) as threads:
            outcomes=list(threads.map(attempt,[first,second]))
        self.assertEqual([x[0] for x in outcomes].count('accepted'),1)
        self.assertEqual([x[0] for x in outcomes].count('rejected'),1)
        approved=next(x[1] for x in outcomes if x[0]=='accepted')
        self.assertEqual(
            registry.inspect(self.registry,1,
                             approved['registry_head_sha256'],
                             approved['latest_checkpoint_sha256'])[
                                 'registry_event_count'],1)

    def test_invalid_signature_does_not_append_any_event(self):
        self.fresh()
        self.first_candidate()
        with self.assertRaises((ValueError, checkpoint.CheckpointConflict)):
            self.accept(signed_a=self.signed_b)
        self.assertEqual(
            registry.inspect(self.registry,0,registry.GENESIS,
                             checkpoint.ANCHOR_GENESIS)['registry_event_count'],0)

    def test_rollback_of_registry_detected_by_externally_pinned_head(self):
        self.fresh()
        self.first_candidate()
        accepted=self.accept()
        with sqlite3.connect(self.registry) as con:
            con.execute('DELETE FROM accepted_replay_checkpoints')
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(
                self.registry,1,accepted['registry_head_sha256'],
                accepted['latest_checkpoint_sha256'])
        # A compromised external escrow can allow genesis to be replayed.
        result=registry.inspect(
            self.registry,0,registry.GENESIS,checkpoint.ANCHOR_GENESIS)
        self.assertFalse(result['durable_hardware_rollback_prevention_proved'])

    def test_corrupt_event_hash_or_header_detected(self):
        self.fresh()
        self.first_candidate()
        accepted=self.accept()
        with sqlite3.connect(self.registry) as con:
            con.execute(
                'UPDATE accepted_replay_checkpoints SET event_sha256=?',
                ('a'*64,))
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(self.registry,1,accepted['registry_head_sha256'],
                             accepted['latest_checkpoint_sha256'])
        with sqlite3.connect(self.registry) as con:
            con.execute('PRAGMA user_version=0')
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(self.registry,1,accepted['registry_head_sha256'],
                             accepted['latest_checkpoint_sha256'])

    def test_unexpected_sqlite_trigger_is_rejected_not_executed(self):
        self.fresh()
        self.first_candidate()
        # An attacker who can modify the registry schema must not be able
        # to add write side effects to an otherwise apparently valid table.
        with sqlite3.connect(self.registry) as con:
            con.execute(
                "CREATE TRIGGER unexpected AFTER INSERT ON "
                "accepted_replay_checkpoints BEGIN SELECT 1; END")
        with self.assertRaises(registry.RegistryConflict):
            self.accept()
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(
                self.registry,0,registry.GENESIS,checkpoint.ANCHOR_GENESIS)

    def test_inserted_fake_chain_event_rejected(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        with sqlite3.connect(self.registry) as con:
            con.execute(
                "UPDATE accepted_replay_checkpoints SET "
                "checkpoint_nonce=? WHERE sequence=1", ('a'*32,))
        with self.assertRaises(registry.RegistryConflict):
            registry.inspect(
                self.registry,1,first['registry_head_sha256'],
                first['latest_checkpoint_sha256'])

    def test_missing_registry_and_symlink_registry_refused(self):
        self.fresh()
        with self.assertRaises(FileExistsError):
            registry.initialize(self.registry)
        target=self.v/'saved-registry.sqlite'
        self.registry.rename(target)
        self.registry.symlink_to(target)
        with self.assertRaises((registry.RegistryConflict, ValueError)):
            registry.inspect(self.registry,0,registry.GENESIS,
                             checkpoint.ANCHOR_GENESIS)
        self.registry.unlink()
        with self.assertRaises(FileNotFoundError):
            registry.inspect(self.registry,0,registry.GENESIS,
                             checkpoint.ANCHOR_GENESIS)

    def test_registry_and_replay_journal_must_be_separate(self):
        self.fresh()
        self.first_candidate()
        with self.assertRaises(registry.RegistryConflict):
            registry.accept(
                self.journal,self.journal,
                self.signed_a,self.signed_b,
                self.admin_a[2],self.admin_a[3],
                self.admin_b[2],self.admin_b[3],
                checkpoint_tag=head_fixture.TAG,
                prior_checkpoint_pin=self.prior,
                candidate_checkpoint_pin=self.checkpoint_pin,
                expected_registry_count=0,
                expected_registry_head=registry.GENESIS,
                expected_latest_checkpoint_pin=checkpoint.ANCHOR_GENESIS)

    def test_registry_scope_cannot_silently_change(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        with self.assertRaises((ValueError, registry.RegistryConflict)):
            self.accept(scope='different-scope',count=1,
                        head=first['registry_head_sha256'],
                        latest=first['latest_checkpoint_sha256'])

    def test_no_partial_publication_on_stale_concurrent_pin(self):
        self.fresh()
        self.first_candidate()
        with self.assertRaises(registry.RegistryConflict):
            self.accept(count=1,head=registry.GENESIS)
        self.assertEqual(registry.inspect(
            self.registry,0,registry.GENESIS,checkpoint.ANCHOR_GENESIS)[
                'registry_event_count'],0)

    def test_registry_records_are_readonly_on_inspection(self):
        self.fresh()
        self.first_candidate()
        first=self.accept()
        before=self.registry.read_bytes()
        registry.inspect(
            self.registry,1,first['registry_head_sha256'],
            first['latest_checkpoint_sha256'])
        self.assertEqual(self.registry.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
