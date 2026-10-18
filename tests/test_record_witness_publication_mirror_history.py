"""Stage 263T: multi-round dual-admin signed mirror history regressions."""
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import unittest

from tests import test_record_witness_publication_mirror_witness as fixture
from tools import audit_record_witness_publication_mirror_history as history
from tools import audit_record_witness_publication_mirror_witness as witness
from tools import audit_record_witness_publication_intake as intake
from tools.audit_record_witness_fence_reconciliation import _sign

TAG='private-wild-arms-publication-mirrors'


class SignedMirrorHistoryTests(unittest.TestCase):
    setUp=fixture.SignedPublicationMirrorWitnessTests.setUp
    path=fixture.SignedPublicationMirrorWitnessTests.path
    request=fixture.SignedPublicationMirrorWitnessTests.request
    stop=fixture.SignedPublicationMirrorWitnessTests.stop
    make_cgroup=fixture.SignedPublicationMirrorWitnessTests.make_cgroup
    write_controls=fixture.SignedPublicationMirrorWitnessTests.write_controls
    snapshot=fixture.SignedPublicationMirrorWitnessTests.snapshot
    signed_stop_for=fixture.SignedPublicationMirrorWitnessTests.signed_stop_for
    new_offer=fixture.SignedPublicationMirrorWitnessTests.new_offer
    make_offer_and_deposit=fixture.SignedPublicationMirrorWitnessTests.make_offer_and_deposit
    init_capture=fixture.SignedPublicationMirrorWitnessTests.init_capture
    build=fixture.SignedPublicationMirrorWitnessTests.build
    prepare=fixture.SignedPublicationMirrorWitnessTests.prepare
    init_journal=fixture.SignedPublicationMirrorWitnessTests.init_journal
    enroll=fixture.SignedPublicationMirrorWitnessTests.enroll
    second_bundle=fixture.SignedPublicationMirrorWitnessTests.second_bundle
    sign_heads=fixture.SignedPublicationMirrorWitnessTests.sign_heads
    fresh=fixture.SignedPublicationMirrorWitnessTests.fresh
    first_candidate=fixture.SignedPublicationMirrorWitnessTests.first_candidate
    accept=fixture.SignedPublicationMirrorWitnessTests.accept
    signed_round=fixture.SignedPublicationMirrorWitnessTests.signed_round
    stage=fixture.SignedPublicationMirrorWitnessTests.stage
    setup_intake=fixture.SignedPublicationMirrorWitnessTests.setup_intake
    submit=fixture.SignedPublicationMirrorWitnessTests.submit
    full_round=fixture.SignedPublicationMirrorWitnessTests.full_round
    conflicting_receipt=fixture.SignedPublicationMirrorWitnessTests.conflicting_receipt
    duplicate=fixture.SignedPublicationMirrorWitnessTests.duplicate

    @classmethod
    def setUpClass(cls):
        fixture.SignedPublicationMirrorWitnessTests.setUpClass()
        for key in ('ca','server_key','server_cert','server_pin',
                    'client_key','client_cert','client_pin',
                    'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,key,getattr(fixture.SignedPublicationMirrorWitnessTests,key))

    @classmethod
    def tearDownClass(cls):
        fixture.SignedPublicationMirrorWitnessTests.tearDownClass()

    def sign_epoch(self,epoch,head,frozen,prior,nonce=None):
        if nonce is None:
            nonce=format(epoch+1,'032x')
        claims={}
        for role,admin in zip(witness.ROLES,self.admins[:2]):
            body=witness.make_body(role,epoch,epoch,head,frozen,prior,nonce,TAG)
            file=self.path('mirror-history-'+role+'-')
            _sign(body,witness.SCHEMA,witness.DOMAIN,admin[1],file)
            claims[role]=file.read_bytes()
        return claims

    def build_history(self,count=0):
        self.setup_intake(0)
        for i in range(count):
            if i<3:
                self.submit(0,('escrow-a','escrow-b','escrow-c')[i])
            elif i==3:
                different=self.conflicting_receipt(0,'escrow-a',nonce='f'*32)
                conflict=self.submit(0,'escrow-a',different)
                self.assertTrue(conflict['signed_conflict_recorded'])
            else:
                raise ValueError('test fixture limited to 4 local events')
        self.mirror_b=self.duplicate()
        events=sqlite3.connect(self.intake_path).execute(
            'SELECT event_sha256,decision FROM published_escrow_receipts '
            'ORDER BY sequence').fetchall()
        claims=[]
        prior=witness.WITNESS_GENESIS
        frozen=False
        for index in range(count+1):
            if index:
                sha,decision=events[index-1]
                if decision=='conflict':
                    frozen=True
            else:
                sha=intake.GENESIS
            round_claims=self.sign_epoch(index,sha,frozen,prior)
            claims.append(round_claims)
            prior=witness.witness_digest(
                round_claims[witness.ROLES[0]],round_claims[witness.ROLES[1]])
        self.claims=claims
        self.latest=prior
        self.archive=history.pack(claims)
        self.archive_pin=hashlib.sha256(self.archive).hexdigest()
        self.archive_file=self.path('signed-mirror-history-')
        self.archive_file.write_bytes(self.archive)
        self.archive_file.chmod(0o600)

    def check(self,*,rounds=None,raw=None,pin=None,latest=None,
              a_count=None,a_head=None,b_count=None,b_head=None,
              a_pub=None,b_pub=None,b_path=None,scope=TAG):
        if rounds is not None:
            raw=history.pack(rounds)
            pin=hashlib.sha256(raw).hexdigest()
        return history.verify(
            self.intake_path,self.i_count if a_count is None else a_count,
            self.i_head if a_head is None else a_head,
            self.mirror_b if b_path is None else b_path,
            self.i_count if b_count is None else b_count,
            self.i_head if b_head is None else b_head,
            self.archive if raw is None else raw,
            self.archive_pin if pin is None else pin,
            self.admins[0][2] if a_pub is None else a_pub,
            self.admins[0][3],
            self.admins[1][2] if b_pub is None else b_pub,
            self.admins[1][3],
            scope=scope,
            expected_latest_witness=self.latest if latest is None else latest)

    def test_signed_genesis_epoch_matches_two_empty_mirrors(self):
        self.build_history(0)
        result=self.check()
        self.assertEqual(result['signed_epoch_count'],1)
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['trusted_global_monotonic_counter_proved'])

    def test_each_published_event_has_exactly_one_signed_epoch(self):
        self.build_history(3)
        result=self.check()
        self.assertEqual(result['signed_epoch_count'],4)
        self.assertEqual(result['mirror_event_count'],3)
        self.assertTrue(result['both_mirror_chains_match_complete_signed_history'])

    def test_conflict_frozen_snapshot_in_final_epoch(self):
        self.build_history(4)
        result=self.check()
        self.assertEqual(result['signed_epoch_count'],5)
        self.assertFalse(result['witness_fence_retired'])

    def test_missing_genesis_epoch_rejected(self):
        self.build_history(1)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=self.claims[1:])

    def test_missing_intermediate_epoch_rejected(self):
        self.build_history(3)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=[self.claims[0],self.claims[2],self.claims[3]])

    def test_duplicate_or_reordered_epochs_rejected(self):
        self.build_history(1)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=[self.claims[0],self.claims[0]])
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=list(reversed(self.claims)))

    def test_signed_intermediate_epoch_must_match_actual_event_hash(self):
        self.build_history(2)
        wrong=self.sign_epoch(1,'f'*64,False,witness.witness_digest(
            self.claims[0][witness.ROLES[0]],
            self.claims[0][witness.ROLES[1]]))
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=[self.claims[0],wrong,self.claims[2]])

    def test_reused_nonce_between_epochs_refused(self):
        self.build_history(1)
        prior=witness.witness_digest(
            self.claims[0][witness.ROLES[0]],
            self.claims[0][witness.ROLES[1]])
        reused=self.sign_epoch(1,self.i_head,False,prior,nonce=format(1,'032x'))
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=[self.claims[0],reused])

    def test_incorrect_signed_predecessor_rejected(self):
        self.build_history(1)
        wrong=self.sign_epoch(1,self.i_head,False,'f'*64)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=[self.claims[0],wrong])

    def test_conflicting_operator_signed_claim_rejected(self):
        self.build_history(1)
        claims=[dict(row) for row in self.claims]
        fake=witness.make_body(
            witness.ROLES[1],1,1,'f'*64,False,
            witness.witness_digest(
                self.claims[0][witness.ROLES[0]],
                self.claims[0][witness.ROLES[1]]),
            format(2,'032x'),TAG)
        signed=self.path('validly-signed-wrong-mirror-')
        _sign(fake,witness.SCHEMA,witness.DOMAIN,self.admins[1][1],signed)
        claims[1][witness.ROLES[1]]=signed.read_bytes()
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(rounds=claims)

    def test_archive_digest_independent_pin_mismatch_refused(self):
        self.build_history(0)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(pin='f'*64)

    def test_latest_witness_external_pin_stale_refused(self):
        self.build_history(1)
        previous=witness.witness_digest(
            self.claims[0][witness.ROLES[0]],
            self.claims[0][witness.ROLES[1]])
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(latest=previous)

    def test_stale_second_mirror_copy_refused(self):
        self.build_history(1)
        with sqlite3.connect(self.mirror_b) as con:
            con.execute('DELETE FROM published_escrow_receipts')
        with self.assertRaises(intake.PublicationConflict):
            self.check()

    def test_valid_but_diverging_second_mirror_refused(self):
        self.build_history(1)
        # The original event hash is independently pinned. A modified row
        # without recomputed hash necessarily fails the complete-chain audit.
        with sqlite3.connect(self.mirror_b) as con:
            con.execute('UPDATE published_escrow_receipts '
                        'SET round_nonce=?',('f'*32,))
        with self.assertRaises(intake.PublicationConflict):
            self.check()

    def test_same_hardlink_mirror_is_never_independent(self):
        self.build_history(0)
        alias=self.v/'same-inode-alias.sqlite'
        os.link(self.intake_path,alias)
        with self.assertRaises(history.MirrorConflict):
            self.check(b_path=alias)

    def test_noncanonical_archive_and_duplicate_json_key_rejected(self):
        self.build_history(0)
        uncanonical=json.dumps(json.loads(self.archive)).encode()
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(raw=uncanonical,
                       pin=hashlib.sha256(uncanonical).hexdigest())
        duplicate=b'{"schema":"a","schema":"b","rounds":[]}\n'
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.check(raw=duplicate,
                       pin=hashlib.sha256(duplicate).hexdigest())

    def test_invalid_signature_not_repaired_by_archive_repin(self):
        self.build_history(1)
        claims=[dict(row) for row in self.claims]
        claims[1][witness.ROLES[1]]=claims[1][witness.ROLES[0]]
        with self.assertRaises(ValueError):
            self.check(rounds=claims)

    def test_missing_role_or_unknown_role_refused(self):
        self.build_history(0)
        with self.assertRaises(history.SnapshotHistoryConflict):
            history.pack([{'mirror-admin-a':self.claims[0][witness.ROLES[0]]}])

    def test_old_db_and_old_signed_pin_replay_remains_possible(self):
        self.build_history(1)
        # A privileged rollback of BOTH journals and the operator's
        # external current pins can present a valid older genesis history.
        for path in (self.intake_path,self.mirror_b):
            with sqlite3.connect(path) as db:
                db.execute('DELETE FROM published_escrow_receipts')
        genesis=self.claims[0]
        old_tip=witness.witness_digest(
            genesis[witness.ROLES[0]],genesis[witness.ROLES[1]])
        result=self.check(
            rounds=[genesis],latest=old_tip,
            a_count=0,b_count=0,
            a_head=intake.GENESIS,b_head=intake.GENESIS)
        self.assertTrue(result['both_mirror_chains_match_complete_signed_history'])
        self.assertFalse(result['old_complete_history_with_old_pins_excluded'])
        self.assertFalse(result['all_hidden_equivocations_discovered'])

    def test_cli_success_is_private_redacted_and_no_unlock(self):
        self.build_history(0)
        args=[
            str(self.intake_path),str(self.mirror_b),
            str(self.archive_file),self.archive_pin,
            '--a-count','0','--a-head',intake.GENESIS,
            '--b-count','0','--b-head',intake.GENESIS,
            '--admin-a-public',str(self.admins[0][2]),
            '--admin-a-public-pin',self.admins[0][3],
            '--admin-b-public',str(self.admins[1][2]),
            '--admin-b-public-pin',self.admins[1][3],
            '--scope',TAG,'--latest-witness-sha256',self.latest,
        ]
        with contextlib.redirect_stdout(buffer := io.StringIO()):
            code=history.main(args)
        self.assertEqual(code,0,buffer.getvalue())
        output=json.loads(buffer.getvalue())
        self.assertFalse(output['witness_fence_retired'])
        self.assertNotIn('signature_hex',buffer.getvalue())
        self.assertNotIn('witness_nonce',buffer.getvalue())


if __name__=='__main__':
    unittest.main()
