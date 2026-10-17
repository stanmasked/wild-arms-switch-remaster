"""Synthetic Stage-262 independently signed fence reconciliation tests.

Includes applied reserve/deposit, failed/uncommitted operations, concurrency,
replay, missing signer, tampered custody evidence, and audit corruption.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from tests.test_record_witness_fence import WitnessFenceTests, A, B, D1
from tests.test_record_custodian_tls import MutualTlsCustodianTests, openssl
from tools.audit_record_anchor_handoff import _canonical, _read_latest, deposit
from tools.audit_record_custodian_reservation import reserve
from tools.audit_record_witness_fence import claim, release, _fence_row, FenceConflict
from tools.audit_record_witness_fence_reconciliation import (
    attest_applied, verify_applied, prepare, approve, recover, main, _audit,
    _request_digest, ReconciliationConflict,
)
from tools.audit_record_recovery_witness import snapshot, record

TOKEN = 'a'*32
OWNER = 'e'*32


class WitnessFenceReconciliationTests(unittest.TestCase):
    make_offer_and_deposit = MutualTlsCustodianTests.make_offer_and_deposit
    setUp = WitnessFenceTests.setUp
    add_unwitnessed_recovery = WitnessFenceTests.add_unwitnessed_recovery
    new_offer = MutualTlsCustodianTests.new_offer

    @classmethod
    def setUpClass(cls):
        WitnessFenceTests.setUpClass()
        for name in ('ca', 'server_key', 'server_cert', 'server_pin',
                     'client_key', 'client_cert', 'client_pin',
                     'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, name, getattr(WitnessFenceTests, name))

    @classmethod
    def tearDownClass(cls):
        WitnessFenceTests.tearDownClass()

    def setUp(self):
        WitnessFenceTests.setUp(self)
        self.admin_dir = self.v/'separate-admins'
        self.admin_dir.mkdir(mode=0o700)
        self.admins = []
        for name in ('alice', 'bob', 'mallory'):
            key = self.admin_dir/(name+'.key')
            public = self.admin_dir/(name+'.pub')
            openssl('genpkey', '-algorithm','ed25519','-out',key)
            openssl('pkey','-in',key,'-pubout','-out',public)
            key.chmod(0o600)
            public.chmod(0o600)
            self.admins.append((name,key,public,
                                hashlib.sha256(public.read_bytes()).hexdigest()))
        self.tag = 'stage262-custodian'
        self.i = 0

    def path(self, prefix):
        self.i += 1
        return self.v/(prefix+str(self.i)+'.json')

    def request(self, action='reserve', *, nonce=OWNER, offer=None):
        row = _read_latest(self.custody)
        request = {
            'schema': 'wild-arms-ps1-mutual-tls-custodian-request-v1',
            'action': action, 'request_id': nonce,
            'expected_sequence': row[0],
            'expected_receipt_sha256': row[3],
            'reservation_token': TOKEN,
        }
        if action == 'deposit-reserved':
            request['checkpoint_b64'] = base64.b64encode(
                offer if offer is not None else self.new_offer()).decode('ascii')
        return _canonical(request)

    def fence(self, original):
        head = (0,'0'*64)
        count, chain = head
        with sqlite3.connect(self.witness_db) as con:
            from tools.audit_record_recovery_witness import _witness_rows
            rows = _witness_rows(con)
            count,chain=len(rows),rows[-1][4] if rows else '0'*64
        req = json.loads(original)
        return claim(self.witness_db, req['request_id'],
                     _request_digest(original), count, chain)

    def outstanding(self):
        with sqlite3.connect(self.witness_db) as con:
            return _fence_row(con)

    def receipt(self, original):
        output = self.path('signed-outcome-')
        result = attest_applied(
            self.custody, original, self.sign_key, output,
            custodian_tag=self.tag)
        return output.read_bytes(), result

    def signed_proposal(self, original, result):
        proposal_file = self.path('reconcile-')
        prepare(self.witness_db, original, result, self.sign_pub,
                self.sign_pub_pin, proposal_file, custodian_tag=self.tag)
        proposal = proposal_file.read_bytes()
        signed = []
        for name, key, _, _ in self.admins[:2]:
            target = self.path('approval-'+name+'-')
            approve(proposal, name, key, target)
            signed.append(target.read_bytes())
        return proposal, tuple(signed)

    def finish(self, original, outcome, proposal, approvals, *, admins=None,
               custody_pin=None):
        a,b = self.admins[:2] if admins is None else admins
        return recover(
            self.witness_db, original, outcome, proposal,
            *approvals, self.sign_pub,
            self.sign_pub_pin if custody_pin is None else custody_pin,
            a[0], a[2], a[3], b[0], b[2], b[3],
            custodian_tag=self.tag)

    def setup_applied_reserve(self):
        raw = self.request()
        self.assertTrue(self.fence(raw))
        head = json.loads(raw)
        self.assertTrue(reserve(
            self.custody, head['expected_sequence'],
            head['expected_receipt_sha256'], TOKEN))
        return raw

    def test_applied_reservation_reconciles_with_two_admins(self):
        original=self.setup_applied_reserve()
        outcome, result=self.receipt(original)
        self.assertEqual(result, 'reservation-observed')
        proposal, approvals=self.signed_proposal(original,outcome)
        self.assertEqual(self.finish(original,outcome,proposal,approvals),1)
        self.assertIsNone(self.outstanding())
        with sqlite3.connect(self.witness_db) as con:
            self.assertEqual(len(_audit(con)),1)
        # A new independently fenced request can be claimed afterward.
        nxt=self.request(nonce='f'*32)
        self.assertTrue(self.fence(nxt))

    def test_committed_checkpoint_observed_and_reconciled(self):
        head=_read_latest(self.custody)
        reserve(self.custody, head[0], head[3], TOKEN)
        offered=self.new_offer()
        original=self.request('deposit-reserved',offer=offered)
        self.assertTrue(self.fence(original))
        self.assertEqual(deposit(
            self.custody,offered, expected_sequence=head[0],
            expected_receipt_sha256=head[3],reservation_token=TOKEN),(2,True))
        outcome,result=self.receipt(original)
        self.assertEqual(result,'checkpoint-committed')
        proposal,approvals=self.signed_proposal(original,outcome)
        self.assertEqual(self.finish(original,outcome,proposal,approvals),1)
        self.assertEqual(_read_latest(self.custody)[0],2)
        self.assertIsNone(self.outstanding())

    def test_not_applied_reserve_stays_fenced(self):
        original=self.request()
        self.fence(original)
        with self.assertRaises(ReconciliationConflict):
            self.receipt(original)
        self.assertIsNotNone(self.outstanding())

    def test_uncommitted_deposit_stays_fenced(self):
        head=_read_latest(self.custody)
        reserve(self.custody,head[0],head[3],TOKEN)
        original=self.request('deposit-reserved',offer=self.new_offer())
        self.fence(original)
        with self.assertRaises(ReconciliationConflict):
            self.receipt(original)
        self.assertIsNotNone(self.outstanding())

    def test_mutated_checkpoint_request_never_reuses_fence(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        different=self.request(nonce='f'*32)
        with self.assertRaises(ValueError):
            self.signed_proposal(different,outcome)
        self.assertIsNotNone(self.outstanding())

    def test_substituted_custodian_public_pem_pin_refused(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        file=self.path('bad-recovery-request-')
        with self.assertRaises(ValueError):
            prepare(self.witness_db,original,outcome,self.sign_pub,
                    'f'*64,file,custodian_tag=self.tag)
        self.assertIsNotNone(self.outstanding())

    def test_tampered_custodian_signature_refused(self):
        original=self.setup_applied_reserve()
        signed,_=self.receipt(original)
        forged=json.loads(signed)
        forged['signature_hex']='0'*128
        with self.assertRaises(ValueError):
            self.signed_proposal(original,_canonical(forged))
        self.assertIsNotNone(self.outstanding())

    def test_replay_admin_approval_for_other_proposal_refused(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,approvals=self.signed_proposal(original,outcome)
        altered=json.loads(proposal)
        altered['recovery_nonce']='f'*32
        with self.assertRaises(ValueError):
            self.finish(original,outcome,_canonical(altered),approvals)
        self.assertIsNotNone(self.outstanding())

    def test_identical_admin_identity_or_key_refused(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,(a,b)=self.signed_proposal(original,outcome)
        alice=self.admins[0]
        with self.assertRaises(ValueError):
            self.finish(original,outcome,proposal,(a,a),admins=(alice,alice))
        with self.assertRaises(ValueError):
            self.finish(original,outcome,proposal,(a,a),
                        admins=(alice,(alice[0]+'2',alice[1],alice[2],alice[3])))
        self.assertIsNotNone(self.outstanding())

    def test_missing_second_admin_signature_refused(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,approvals=self.signed_proposal(original,outcome)
        with self.assertRaises(ValueError):
            self.finish(original,outcome,proposal,(approvals[0],b'{}'))
        self.assertIsNotNone(self.outstanding())

    def test_exactly_one_concurrent_recovery_succeeds(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,approvals=self.signed_proposal(original,outcome)
        def attempt(_):
            try:
                return self.finish(original,outcome,proposal,approvals)
            except ReconciliationConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers=list(pool.map(attempt,range(2)))
        self.assertEqual(answers.count(1),1)
        self.assertEqual(answers.count(None),1)
        with sqlite3.connect(self.witness_db) as con:
            self.assertEqual(len(_audit(con)),1)

    def test_repeat_old_authorization_does_not_retire_new_fence(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,approvals=self.signed_proposal(original,outcome)
        self.assertEqual(self.finish(original,outcome,proposal,approvals),1)
        next_request=self.request(nonce='f'*32)
        self.fence(next_request)
        with self.assertRaises(ReconciliationConflict):
            self.finish(original,outcome,proposal,approvals)
        self.assertIsNotNone(self.outstanding())

    def test_changed_witness_owner_blocks_previously_authorized_recovery(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,approvals=self.signed_proposal(original,outcome)
        req=json.loads(original)
        release(self.witness_db, req['request_id'],_request_digest(original))
        self.fence(self.request(nonce='f'*32))
        with self.assertRaises(ReconciliationConflict):
            self.finish(original,outcome,proposal,approvals)
        self.assertIsNotNone(self.outstanding())

    def test_audit_hash_corruption_blocks_claim_release_and_record(self):
        original=self.setup_applied_reserve()
        outcome,_=self.receipt(original)
        proposal,approvals=self.signed_proposal(original,outcome)
        self.finish(original,outcome,proposal,approvals)
        with sqlite3.connect(self.witness_db) as con:
            con.execute('UPDATE witness_fence_reconciliations SET event_sha256=?',
                        ('f'*64,))
        with self.assertRaises(ValueError):
            self.fence(self.request(nonce='f'*32))
        with self.assertRaises(ValueError):
            release(self.witness_db,'f'*32,'a'*64)
        # Supply an otherwise valid newly observed recovery event, so
        # failure must arise from the corrupted reconciliation audit.
        self.add_unwitnessed_recovery()
        valid_snapshot = _canonical(snapshot(self.custody))
        with self.assertRaisesRegex(ValueError, 'corrupt reconciliation'):
            record(self.witness_db, valid_snapshot)

    def test_invalid_or_unsupported_legacy_request_refused(self):
        item=json.loads(self.request())
        item['action']='deposit'
        with self.assertRaises(ValueError):
            attest_applied(self.custody,_canonical(item),self.sign_key,
                           self.path('not-supported-'),custodian_tag=self.tag)

    def test_cli_attest_and_approval_reports_have_no_secrets(self):
        original=self.setup_applied_reserve()
        request_path=self.path('original-request-')
        request_path.write_bytes(original)
        request_path.chmod(0o600)
        signed_path=self.path('custody-signed-')
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rc=main(['attest',str(self.custody),str(request_path),
                     str(self.sign_key),str(signed_path),
                     '--custodian-tag',self.tag])
        self.assertEqual(rc,0)
        self.assertTrue(json.loads(out.getvalue())[
            'custody_operation_observed_applied'])
        proposal_path=self.path('proposal-')
        with contextlib.redirect_stdout(out:=io.StringIO()):
            rc=main(['prepare',str(self.witness_db),str(request_path),
                     str(signed_path),str(self.sign_pub),self.sign_pub_pin,
                     str(proposal_path),'--custodian-tag',self.tag])
        self.assertEqual(rc,0)
        approvals=[]
        for name,key,_,_ in self.admins[:2]:
            dest=self.path('admin-proof-')
            with contextlib.redirect_stdout(out:=io.StringIO()):
                rc=main(['approve',str(proposal_path),name,str(key),str(dest)])
            self.assertEqual(rc,0)
            approvals.append(dest)
        alice,bob=self.admins[:2]
        args=[
            'recover',str(self.witness_db),str(request_path),str(signed_path),
            str(proposal_path),str(approvals[0]),str(approvals[1]),
            str(self.sign_pub),self.sign_pub_pin,
            alice[0],str(alice[2]),alice[3],
            bob[0],str(bob[2]),bob[3],
            '--custodian-tag',self.tag,
        ]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            self.assertEqual(main(args),0)
        self.assertTrue(json.loads(out.getvalue())['orphaned_applied_fence_retired'])
        self.assertNotIn(self.sign_pub_pin,out.getvalue())
        self.assertNotIn(TOKEN,out.getvalue())


if __name__=='__main__':
    unittest.main()
