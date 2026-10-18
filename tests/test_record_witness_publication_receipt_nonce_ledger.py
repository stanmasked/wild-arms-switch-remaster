"""Stage 264J local atomic pre-sign nonce consumption, pending and replay tests."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import unittest

from tests import test_record_witness_publication_replica_receipts as fixture
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_replica_receipt_sign as signer
from tools import audit_record_witness_publication_checkpoint_cas as cas


class ReceiptNonceLedgerTests(unittest.TestCase):
    setUpClass=fixture.ReplicaReceiptTests.__dict__['setUpClass']
    tearDownClass=fixture.ReplicaReceiptTests.__dict__['tearDownClass']
    sign=fixture.ReplicaReceiptTests.sign
    compute_pin=fixture.ReplicaReceiptTests.compute_pin
    fetch=fixture.ReplicaReceiptTests.fetch
    _advanced_keeper=fixture.ReplicaReceiptTests._advanced_keeper
    certificate=fixture.ReplicaReceiptTests.certificate
    body=fixture.ReplicaReceiptTests.body
    endorse=fixture.ReplicaReceiptTests.endorse
    bundle=fixture.ReplicaReceiptTests.bundle
    args=fixture.ReplicaReceiptTests.args
    check=fixture.ReplicaReceiptTests.check
    create=fixture.ReplicaReceiptTests.create
    inspect=fixture.ReplicaReceiptTests.inspect
    arguments=fixture.ReplicaReceiptTests.arguments
    copy_args=fixture.ReplicaReceiptTests.copy_args
    clone=fixture.ReplicaReceiptTests.clone
    signed_body=fixture.ReplicaReceiptTests.signed_body
    sign_receipt=fixture.ReplicaReceiptTests.sign_receipt
    params=fixture.ReplicaReceiptTests.params
    verify=fixture.ReplicaReceiptTests.verify
    attest=fixture.ReplicaReceiptTests.attest
    operator_args=fixture.ReplicaReceiptTests.operator_args

    def setUp(self):
        fixture.ReplicaReceiptTests.setUp(self)

    def make_fields(self,idx=0,nonce=None,seq=1,previous=None):
        letter=('a','b')[idx]
        return dict(scope=self.scope,role='operator-'+letter,
            operator_id='private-operator-'+letter,
            storage_id='private-store-'+letter,
            operator_public_pin=self.observers[idx][2],
            nonce=self.nonces[idx] if nonce is None else nonce,
            seq=seq,
            previous=self.previous_receipts[idx] if previous is None else previous,
            archive_pin=self.primary_pin,evidence_pin=self.evidence_sha)

    def reserve(self,idx=0,nonce=None,head=None,seq=1,previous=None):
        return ledger._record(self.registry_path,action='reserve',
            expected_head=self.registry_genesis if head is None else head,
            **self.make_fields(idx,nonce,seq,previous))

    def sign_one(self,idx=0,argv=None):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=signer.main(self.operator_args(idx) if argv is None else argv)
        return status,json.loads(out.getvalue())

    def test_enrolled_genesis_has_no_events(self):
        s=ledger.snapshot(self.registry_path,expected_ledger_head=self.registry_genesis)
        self.assertEqual(s['event_count'],0)
        self.assertEqual(s['pending_operator_roles'],[])
        self.assertEqual(s['latest_ledger_sha256'],self.registry_genesis)

    def test_guarded_operator_cli_consumes_before_signature(self):
        status,report=self.sign_one()
        self.assertEqual(status,0,report)
        self.assertTrue(report['nonce_consumed_before_receipt_signing'])
        self.assertTrue(report['nonce_ledger_completed_with_exact_signed_receipt'])
        snapshot=ledger.snapshot(self.registry_path,
            expected_ledger_head=report['latest_ledger_sha256'])
        self.assertEqual(snapshot['event_count'],2)
        self.assertEqual(snapshot['completed_operator_sequences']['operator-a'],1)
        self.assertFalse(report['offhost_monotonic_nonce_cas_proved'])

    def test_repeated_signed_receipt_cannot_reuse_nonce(self):
        status,report=self.sign_one()
        self.assertEqual(status,0,report)
        args=self.operator_args(0)
        args[1]=str(Path(self.temp.name)/'different-receipt.json')
        head_at=args.index('--expected-registry-head')
        args[head_at+1]=report['latest_ledger_sha256']
        seq=args.index('--receipt-sequence')
        args[seq+1]='2'
        previous=args.index('--previous-receipt-sha256')
        args[previous+1]=report['receipt_envelope_sha256']
        status2,result=self.sign_one(argv=args)
        self.assertEqual(status2,1)
        self.assertTrue(result['receipt_conflict'])
        self.assertFalse(Path(args[1]).exists())
        snapshot=ledger.snapshot(self.registry_path)
        self.assertEqual(snapshot['event_count'],2)

    def test_new_nonce_after_signed_previous_works(self):
        status,report=self.sign_one()
        self.assertEqual(status,0,report)
        args=self.operator_args(0)
        args[1]=str(Path(self.temp.name)/'next-receipt.json')
        for flag,value in (
                ('--expected-registry-head',report['latest_ledger_sha256']),
                ('--challenge','c'*32),
                ('--receipt-sequence','2'),
                ('--previous-receipt-sha256',report['receipt_envelope_sha256'])):
            args[args.index(flag)+1]=value
        s,r=self.sign_one(argv=args)
        self.assertEqual(s,0,r)
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],4)
        self.assertNotEqual(r['latest_ledger_sha256'],report['latest_ledger_sha256'])

    def test_nonce_is_globally_unique_even_across_both_roles(self):
        reserved=self.reserve(0)
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.reserve(1,nonce=self.nonces[0],head=reserved)
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],1)

    def test_pending_operator_cannot_sign_other_nonce(self):
        head=self.reserve(0)
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.reserve(0,nonce='c'*32,head=head)

    def test_different_operator_can_reserve_while_first_pending(self):
        first=self.reserve(0)
        second=self.reserve(1,head=first)
        snapshot=ledger.snapshot(self.registry_path,expected_ledger_head=second)
        self.assertEqual(snapshot['pending_operator_roles'],
                         ['operator-a','operator-b'])

    def test_pre_sign_failure_burns_reservation_permanently(self):
        args=self.operator_args(0)
        args[args.index('--evidence-sha256')+1]='f'*64
        status,result=self.sign_one(argv=args)
        self.assertEqual(status,1)
        self.assertTrue(result['receipt_conflict'])
        self.assertFalse(self.receipt_paths[0].exists())
        snapshot=ledger.snapshot(self.registry_path)
        self.assertEqual(snapshot['pending_operator_roles'],['operator-a'])
        self.assertEqual(snapshot['event_count'],1)
        again=self.operator_args(0)
        again[again.index('--expected-registry-head')+1]=snapshot['latest_ledger_sha256']
        status2,_=self.sign_one(argv=again)
        self.assertEqual(status2,1)
        self.assertFalse(self.receipt_paths[0].exists())
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],1)

    def test_wrong_expected_latest_head_blocks_without_consumption(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='reserve',
                expected_head='f'*64,**self.make_fields())
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],0)

    def test_missing_database_is_not_recreated(self):
        self.registry_path.unlink()
        with self.assertRaises((ValueError,OSError)):
            self.reserve()
        self.assertFalse(self.registry_path.exists())

    def test_wrong_operator_id_blocks(self):
        fields=self.make_fields()
        fields['operator_id']='attacker'
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='reserve',
                expected_head=self.registry_genesis,**fields)

    def test_wrong_operator_public_enrollment_blocks(self):
        fields=self.make_fields()
        fields['operator_public_pin']='f'*64
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='reserve',
                expected_head=self.registry_genesis,**fields)

    def test_wrong_storage_enrollment_blocks(self):
        fields=self.make_fields()
        fields['storage_id']='new-storage'
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='reserve',
                expected_head=self.registry_genesis,**fields)

    def test_same_nonce_race_allows_only_one_committed_reservation(self):
        fields=self.make_fields()
        def attempt(_):
            try:
                return ledger._record(self.registry_path,
                    action='reserve',expected_head=self.registry_genesis,**fields)
            except (ledger.NonceLedgerConflict,sqlite3.DatabaseError):
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            out=list(pool.map(attempt,range(2)))
        self.assertEqual(len([x for x in out if x is not None]),1)
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],1)

    def test_duplicate_sequence_with_different_nonce_is_rejected(self):
        head=self.reserve()
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.reserve(nonce='c'*32,head=head,seq=1)

    def test_complete_without_previous_reservation_refused(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='complete',
                expected_head=self.registry_genesis,receipt_pin='e'*64,
                **self.make_fields())
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],0)

    def test_commit_requires_exact_pending_nonce(self):
        head=self.reserve()
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='complete',
                expected_head=head,receipt_pin='e'*64,
                **self.make_fields(nonce='c'*32))

    def test_commit_requires_nonzero_receipt_digest(self):
        head=self.reserve()
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='complete',
                expected_head=head,receipt_pin=cas.ZERO,**self.make_fields())

    def test_hash_chain_tampering_detected(self):
        self.reserve()
        with sqlite3.connect(self.registry_path) as con:
            con.execute("UPDATE events SET archive_sha256=? WHERE event_id=1",
                        ('e'*64,))
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger.snapshot(self.registry_path)

    def test_dropped_reserved_event_detected_by_external_pin(self):
        head=self.reserve()
        with sqlite3.connect(self.registry_path) as con:
            con.execute('DELETE FROM events')
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],0)
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger.snapshot(self.registry_path,expected_ledger_head=head)

    def test_scope_mismatch_rejected_without_consumption(self):
        fields=self.make_fields()
        fields['scope']='untrusted-scope'
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='reserve',
                expected_head=self.registry_genesis,**fields)

    def test_same_scope_but_wrong_expected_previous_pin_rejected(self):
        fields=self.make_fields()
        fields['previous']='d'*64
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger._record(self.registry_path,action='reserve',
                expected_head=self.registry_genesis,**fields)

    def test_genesis_signature_identity_changes_hash(self):
        alternative={role:dict(e) for role,e in self.registry_enrollment.items()}
        alternative['operator-a']['public_pin']='f'*64
        self.assertNotEqual(ledger.genesis_digest(self.scope,alternative),
                            self.registry_genesis)

    def test_genesis_requires_distinct_public_key_pins(self):
        bad={role:dict(e) for role,e in self.registry_enrollment.items()}
        bad['operator-b']['public_pin']=bad['operator-a']['public_pin']
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger.genesis_digest(self.scope,bad)

    def test_genesis_wrong_external_pin_does_not_create(self):
        path=Path(self.temp.name)/'another-ledger.db'
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger.init(path,scope=self.scope,enrollment=self.registry_enrollment,
                        independent_genesis_pin='f'*64)
        self.assertFalse(path.exists())

    def test_genesis_cannot_overwrite_existing_db(self):
        with self.assertRaises(FileExistsError):
            ledger.init(self.registry_path,scope=self.scope,
                enrollment=self.registry_enrollment,
                independent_genesis_pin=self.registry_genesis)

    def test_registry_private_permissions_enforced(self):
        self.registry_path.chmod(0o644)
        with self.assertRaises((ValueError,ledger.NonceLedgerConflict)):
            ledger.snapshot(self.registry_path)

    def test_registry_symlink_rejected(self):
        alias=Path(self.temp.name)/'alias-registry.db'
        alias.symlink_to(self.registry_path)
        with self.assertRaises((ValueError,ledger.NonceLedgerConflict)):
            ledger.snapshot(alias)

    def test_registry_private_parent_enforced(self):
        path=self.registry_path.parent
        path.chmod(0o755)
        self.addCleanup(path.chmod,0o700)
        with self.assertRaises(ledger.NonceLedgerConflict):
            ledger.snapshot(self.registry_path)

    def test_failed_command_returns_redacted_json_no_release(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=ledger.main(['audit',str(self.registry_path),
                               '--expected-ledger-head','f'*64])
        report=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertTrue(report['nonce_ledger_conflict'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertFalse(report['automatic_cas_retry_authorized'])
        self.assertNotIn('private-operator',out.getvalue())

    def test_cli_explicit_init_and_audit(self):
        path=Path(self.temp.name)/'separate-ledger.db'
        args=['init',str(path),'--scope',self.scope,
              '--expected-genesis-pin',self.registry_genesis]
        for letter,idx in (('a',0),('b',1)):
            for flag,value in (
                ('operator-'+letter+'-id','private-operator-'+letter),
                ('storage-'+letter+'-id','private-store-'+letter),
                ('operator-'+letter+'-public',str(self.observers[idx][1])),
                ('operator-'+letter+'-pin',self.observers[idx][2]),
                ('operator-'+letter+'-initial-previous-sha256',
                 self.previous_receipts[idx])):
                args.extend(['--'+flag,value])
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=ledger.main(args)
        self.assertEqual(status,0,out.getvalue())
        with contextlib.redirect_stdout(check:=io.StringIO()):
            status=ledger.main(['audit',str(path),
                '--expected-ledger-head',self.registry_genesis])
        self.assertEqual(status,0,check.getvalue())
        self.assertEqual(json.loads(check.getvalue())['event_count'],0)

    def test_report_never_claims_independent_external_cas(self):
        code,report=self.sign_one()
        self.assertEqual(code,0)
        self.assertFalse(report['offhost_monotonic_nonce_cas_proved'])
        self.assertFalse(report['independently_retained_latest_ledger_proved'])
        self.assertFalse(report['witness_fence_retired'])

    def test_reuse_after_failed_sign_blocked_even_when_new_head_supplied(self):
        wrong=self.operator_args(0)
        wrong[wrong.index('--signing-private')+1]=str(self.observers[1][0])
        status,_=self.sign_one(argv=wrong)
        self.assertEqual(status,1)
        audit=ledger.snapshot(self.registry_path)
        self.assertEqual(audit['pending_operator_roles'],['operator-a'])
        args=self.operator_args(0)
        args[args.index('--expected-registry-head')+1]=audit['latest_ledger_sha256']
        status,_=self.sign_one(argv=args)
        self.assertEqual(status,1)
        self.assertEqual(ledger.snapshot(self.registry_path)['event_count'],1)


if __name__=='__main__':
    unittest.main()
