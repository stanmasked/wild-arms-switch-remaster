"""Stage 263Q: signed publication intake replay, equivocation and CAS tests."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
import sqlite3
import unittest

from tests import test_record_witness_escrow_history as fixture
from tools import audit_record_witness_publication_intake as intake
from tools import audit_record_witness_escrow_quorum as escrow
from tools import audit_record_witness_checkpoint_registry as registry
from tools import audit_record_witness_replay_head_checkpoint as checkpoint
from tools.audit_record_witness_fence_reconciliation import _sign


class SignedPublicationIntakeTests(unittest.TestCase):
    setUp = fixture.EscrowHistoryTests.setUp
    path = fixture.EscrowHistoryTests.path
    request = fixture.EscrowHistoryTests.request
    stop = fixture.EscrowHistoryTests.stop
    make_cgroup = fixture.EscrowHistoryTests.make_cgroup
    write_controls = fixture.EscrowHistoryTests.write_controls
    snapshot = fixture.EscrowHistoryTests.snapshot
    signed_stop_for = fixture.EscrowHistoryTests.signed_stop_for
    new_offer = fixture.EscrowHistoryTests.new_offer
    make_offer_and_deposit = fixture.EscrowHistoryTests.make_offer_and_deposit
    init_capture = fixture.EscrowHistoryTests.init_capture
    build = fixture.EscrowHistoryTests.build
    prepare = fixture.EscrowHistoryTests.prepare
    init_journal = fixture.EscrowHistoryTests.init_journal
    enroll = fixture.EscrowHistoryTests.enroll
    second_bundle = fixture.EscrowHistoryTests.second_bundle
    sign_heads = fixture.EscrowHistoryTests.sign_heads
    fresh = fixture.EscrowHistoryTests.fresh
    first_candidate = fixture.EscrowHistoryTests.first_candidate
    accept = fixture.EscrowHistoryTests.accept
    signed_round = fixture.EscrowHistoryTests.signed_round
    stage = fixture.EscrowHistoryTests.stage

    @classmethod
    def setUpClass(cls):
        fixture.EscrowHistoryTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(fixture.EscrowHistoryTests,name))

    @classmethod
    def tearDownClass(cls):
        fixture.EscrowHistoryTests.tearDownClass()

    def setup_intake(self, count=1):
        self.stage(count)
        self.intake_path = self.v/'operator-publications.sqlite'
        initialized = intake.initialize(self.intake_path)
        self.assertFalse(initialized['witness_fence_retirement_authorized'])
        self.i_count = 0
        self.i_head = intake.GENESIS

    def submit(self, round_number,role,raw=None, *,
               expected_count=None,expected_head=None,
               registry_count=None,registry_head=None,
               registry_checkpoint=None,key_role=None,scope=fixture.TAG,
               advance=True):
        key_role = role if key_role is None else key_role
        src = self.rounds[round_number][role] if raw is None else raw
        result=intake.submit(
            self.intake_path,self.registry,src,role,
            self.keys[key_role],self.pins[key_role],
            checkpoint_tag=scope,
            expected_intake_count=(
                self.i_count if expected_count is None else expected_count),
            expected_intake_head=(
                self.i_head if expected_head is None else expected_head),
            expected_registry_count=(
                self.current_count if registry_count is None
                else registry_count),
            expected_registry_head=(
                self.current_head if registry_head is None
                else registry_head),
            expected_registry_checkpoint=(
                self.current_checkpoint if registry_checkpoint is None
                else registry_checkpoint))
        if advance:
            self.i_count = result['intake_event_count']
            self.i_head = result['intake_head_sha256']
        return result

    def full_round(self,number):
        return [self.submit(number,role) for role in escrow.ROLES]

    def conflicting_receipt(self,number,role, *,
                            nonce=None,head=None,prior=None,checkpoint_pin=None):
        body=json.loads(self.rounds[number][role])['body']
        body['escrow_round_nonce'] = (body['escrow_round_nonce']
                                      if nonce is None else nonce)
        body['registry_head_sha256'] = (body['registry_head_sha256']
                                        if head is None else head)
        body['previous_escrow_sha256'] = (body['previous_escrow_sha256']
                                         if prior is None else prior)
        body['latest_checkpoint_sha256'] = (
            body['latest_checkpoint_sha256'] if checkpoint_pin is None
            else checkpoint_pin)
        file=self.path('signed-intake-variant-')
        _sign(body,escrow.SCHEMA,escrow.DOMAIN,
              self.admins[escrow.ROLES.index(role)][1],file)
        return file.read_bytes()

    def test_new_intake_is_private_read_only_inspect_and_advisory(self):
        self.setup_intake(0)
        result=intake.inspect(self.intake_path,0,intake.GENESIS)
        self.assertEqual(result['intake_event_count'],0)
        self.assertEqual(self.intake_path.stat().st_mode & 0o077,0)
        self.assertFalse(result['complete_remote_publication_proved'])
        self.assertFalse(result['witness_fence_retired'])

    def test_all_genesis_receipts_are_individually_recorded(self):
        self.setup_intake(0)
        responses=self.full_round(0)
        self.assertEqual(self.i_count,3)
        self.assertTrue(all(z['new_receipt_accepted'] for z in responses))
        self.assertFalse(any(z['signed_conflict_recorded'] for z in responses))
        self.assertEqual(intake.inspect(
            self.intake_path,3,self.i_head)['intake_event_count'],3)

    def test_full_genesis_and_successor_with_separate_publications(self):
        self.setup_intake(1)
        self.full_round(0)
        self.full_round(1)
        self.assertEqual(self.i_count,6)
        result=intake.inspect(self.intake_path,6,self.i_head)
        self.assertFalse(result['intake_frozen_by_conflict'])

    def test_repeated_exact_receipt_is_rejected_without_append(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        with self.assertRaises(intake.PublicationConflict):
            self.submit(0,'escrow-a')
        self.assertEqual(intake.inspect(
            self.intake_path,1,self.i_head)['intake_event_count'],1)

    def test_different_valid_signature_for_same_slot_is_logged_and_frozen(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        different=self.conflicting_receipt(
            0,'escrow-a',nonce='a'*32)
        result=self.submit(0,'escrow-a',different)
        self.assertTrue(result['signed_conflict_recorded'])
        self.assertTrue(result['intake_frozen_by_conflict'])
        self.assertFalse(result['new_receipt_accepted'])
        with self.assertRaises(intake.PublicationConflict):
            self.submit(0,'escrow-b')
        self.assertTrue(intake.inspect(
            self.intake_path,2,self.i_head)['intake_frozen_by_conflict'])

    def test_disagreeing_operator_same_round_nonce_is_recorded(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        other=self.conflicting_receipt(0,'escrow-b',nonce='a'*32)
        result=self.submit(0,'escrow-b',other)
        self.assertTrue(result['signed_conflict_recorded'])
        self.assertEqual(self.i_count,2)

    def test_wrong_but_validly_signed_registry_digest_logged(self):
        self.setup_intake(1)
        self.full_round(0)
        signed=self.conflicting_receipt(1,'escrow-a',head='f'*64)
        result=self.submit(1,'escrow-a',signed)
        self.assertTrue(result['signed_conflict_recorded'])

    def test_skipping_unpublished_genesis_round_is_recorded(self):
        self.setup_intake(1)
        result=self.submit(1,'escrow-a')
        self.assertTrue(result['signed_conflict_recorded'])
        self.assertTrue(result['intake_frozen_by_conflict'])

    def test_wrong_predecessor_escrow_bundle_logged(self):
        self.setup_intake(1)
        self.full_round(0)
        signed=self.conflicting_receipt(1,'escrow-a',prior='e'*64)
        self.assertTrue(self.submit(
            1,'escrow-a',signed)['signed_conflict_recorded'])

    def test_nonce_reused_across_two_rounds_logged(self):
        self.setup_intake(1)
        self.full_round(0)
        old=json.loads(self.rounds[0]['escrow-a'])['body']['escrow_round_nonce']
        signed=self.conflicting_receipt(1,'escrow-a',nonce=old)
        self.assertTrue(self.submit(
            1,'escrow-a',signed)['signed_conflict_recorded'])

    def test_wrong_external_head_and_stale_count_refused(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        for count,head in ((0,intake.GENESIS),(1,'f'*64),(-1,self.i_head)):
            with self.subTest(count=count,head=head):
                with self.assertRaises(intake.PublicationConflict):
                    intake.inspect(self.intake_path,count,head)

    def test_wrong_independent_registry_pin_refused_without_write(self):
        self.setup_intake(0)
        with self.assertRaises(registry.RegistryConflict):
            self.submit(0,'escrow-a',registry_head='f'*64)
        self.assertEqual(self.i_count,0)
        self.assertEqual(intake.inspect(
            self.intake_path,0,intake.GENESIS)['intake_event_count'],0)

    def test_forged_signer_or_tampered_envelope_is_rejected(self):
        self.setup_intake(0)
        with self.assertRaises(ValueError):
            self.submit(0,'escrow-a',key_role='escrow-b')
        damaged=self.rounds[0]['escrow-a'].replace(b'escrow-a',b'escrow-x')
        with self.assertRaises(ValueError):
            self.submit(0,'escrow-a',damaged)
        self.assertEqual(self.i_count,0)

    def test_two_concurrent_same_tip_only_one_append(self):
        self.setup_intake(0)
        def publish(_):
            try:
                return ('success',self.submit(
                    0,'escrow-a',advance=False))
            except intake.PublicationConflict:
                return ('rejected',None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(publish,range(2)))
        self.assertEqual([z[0] for z in results].count('success'),1)
        self.assertEqual([z[0] for z in results].count('rejected'),1)
        approved=next(v for status,v in results if status=='success')
        self.assertEqual(intake.inspect(
            self.intake_path,1,approved['intake_head_sha256'])[
                'intake_event_count'],1)

    def test_two_concurrent_conflicting_heads_do_not_replace_first(self):
        self.setup_intake(0)
        different=self.conflicting_receipt(
            0,'escrow-a',nonce='a'*32)
        first=self.submit(0,'escrow-a')
        variant=self.submit(0,'escrow-a',different)
        self.assertTrue(variant['signed_conflict_recorded'])
        with sqlite3.connect(self.intake_path) as conn:
            rows=conn.execute(
                'SELECT decision,original_receipt_sha256 '
                'FROM published_escrow_receipts ORDER BY sequence').fetchall()
        self.assertEqual(rows[0][0],'accepted')
        self.assertEqual(rows[1][0],'conflict')
        self.assertEqual(rows[1][1],
                         hashlib.sha256(self.rounds[0]['escrow-a']).hexdigest())
        self.assertNotEqual(first['intake_head_sha256'],
                            variant['intake_head_sha256'])

    def test_local_chain_mutation_detected(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        with sqlite3.connect(self.intake_path) as con:
            con.execute('UPDATE published_escrow_receipts '
                        'SET round_nonce=?',( 'f'*32,))
        with self.assertRaises(intake.PublicationConflict):
            intake.inspect(self.intake_path,1,self.i_head)

    def test_sqlite_trigger_injection_is_refused(self):
        self.setup_intake(0)
        with sqlite3.connect(self.intake_path) as conn:
            conn.execute('CREATE TRIGGER extra AFTER INSERT ON '
                         'published_escrow_receipts BEGIN SELECT 1; END')
        with self.assertRaises(intake.PublicationConflict):
            intake.inspect(self.intake_path,0,intake.GENESIS)

    def test_rollback_detected_only_against_external_head(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        first=self.i_head
        with sqlite3.connect(self.intake_path) as con:
            con.execute('DELETE FROM published_escrow_receipts')
        with self.assertRaises(intake.PublicationConflict):
            intake.inspect(self.intake_path,1,first)
        restored=intake.inspect(self.intake_path,0,intake.GENESIS)
        self.assertFalse(restored['rollback_prevention_proved'])

    def test_symlinked_or_missing_intake_refused_no_implicit_recreation(self):
        self.setup_intake(0)
        target=self.v/'saved-intake.sqlite'
        self.intake_path.rename(target)
        self.intake_path.symlink_to(target)
        with self.assertRaises((ValueError,intake.PublicationConflict)):
            intake.inspect(self.intake_path,0,intake.GENESIS)
        self.intake_path.unlink()
        with self.assertRaises(FileNotFoundError):
            intake.inspect(self.intake_path,0,intake.GENESIS)

    def test_cli_redacted_inspection_no_unlock(self):
        self.setup_intake(0)
        with contextlib.redirect_stdout(out := io.StringIO()):
            code=intake.main([
                'inspect',str(self.intake_path),
                '--expected-count','0','--expected-head',intake.GENESIS])
        self.assertEqual(code,0)
        report=json.loads(out.getvalue())
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__ == '__main__':
    unittest.main()
