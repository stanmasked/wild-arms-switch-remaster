"""Stage 264S: guarded Ed25519 mirror acknowledgment, pending and replay."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unittest

from tests import test_record_witness_publication_signed_mirror_acknowledgments as base
from tools import audit_record_witness_publication_mirror_ack_nonce_guard as guard
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_signed_mirror_acknowledgments as mirror
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools import audit_record_witness_publication_attestation_registry_binding as binding


class MirrorAcknowledgmentNonceGuardTests(unittest.TestCase):
    setUpClass=base.SignedMirrorAcknowledgmentTests.__dict__['setUpClass']
    tearDownClass=base.SignedMirrorAcknowledgmentTests.__dict__['tearDownClass']

    def setUp(self):
        base.SignedMirrorAcknowledgmentTests.setUp(self)
        self.ack_registry=Path(self.temp.name)/'separate-mirror-ack-nonce-ledger.db'
        self.stores=('mirror-ack-store-a','mirror-ack-store-b')
        self.ack_enrollment={
            role:{
                'operator_id':'fork-witness-operator-'+letter,
                'storage_id':self.stores[i],
                'public_pin':self.observers[i][2],
                'initial_previous_sha256':self.previous[i]}
            for i,(role,letter) in enumerate(
                (('operator-a','a'),('operator-b','b')))}
        self.ack_genesis=ledger.genesis_digest(self.scope,self.ack_enrollment)
        ledger.init(self.ack_registry,scope=self.scope,
            enrollment=self.ack_enrollment,
            independent_genesis_pin=self.ack_genesis)

    def arguments(self,i=0,**changes):
        p=self.params()
        d=dict(
            signed_envelopes=self.complete,head_a=p['primary_head_pin'],
            head_b=p['secondary_head_pin'],genesis_a=self.genesis,
            genesis_b=self.genesis,scope=self.scope,audit_id=self.audit_id,
            role=('operator-a','operator-b')[i],
            operator_id='fork-witness-operator-'+('a','b')[i],
            storage_id=self.stores[i],nonce=self.nonces[i],sequence=1,
            previous_ack_sha256=self.previous[i],
            public_a=self.observers[0][1],public_b=self.observers[1][1],
            signing_private=self.observers[i][0],
            signing_public=self.observers[i][1],
            signing_public_pin=self.observers[i][2],
            expected_registry_head=self.ack_genesis,
            output=self.paths[i])
        d.update(changes)
        return d

    def guarded(self,i=0,**changes):
        return guard.guarded_sign(self.guard_path,self.mirror,self.ack_registry,
                                 **self.arguments(i,**changes))

    def snapshot(self):
        return ledger.snapshot(self.ack_registry)

    def test_first_guarded_signature_commits_exact_two_events(self):
        r=self.guarded()
        self.assertTrue(r['nonce_reserved_before_ed25519_signature'])
        self.assertTrue(r['signed_acknowledgment_reverified_before_completion'])
        self.assertEqual(r['acknowledgment_sha256'],
                         hashlib.sha256(self.paths[0].read_bytes()).hexdigest())
        state=ledger.snapshot(self.ack_registry,
                              expected_ledger_head=r['latest_ack_registry_sha256'])
        self.assertEqual(state['event_count'],2)
        self.assertEqual(state['pending_operator_roles'],[])
        self.assertEqual(state['completed_operator_sequences']['operator-a'],1)

    def test_second_role_can_sign_after_first_ack_committed(self):
        a=self.guarded()
        b=self.guarded(1,expected_registry_head=a['latest_ack_registry_sha256'])
        self.assertEqual(self.snapshot()['event_count'],4)
        self.assertTrue(b['mirror_full_signature_audit_ran_before_and_after_signing'])
        report=self.verify(
            signed_a=self.paths[0].read_bytes(),signed_b=self.paths[1].read_bytes(),
            ack_a_pin=a['acknowledgment_sha256'],ack_b_pin=b['acknowledgment_sha256'])
        self.assertTrue(report['two_independently_sha256_pinned_ed25519_mirror_receipts_verified'])

    def test_same_nonce_globally_refused_between_roles(self):
        a=self.guarded()
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(1,nonce=self.nonces[0],
                expected_registry_head=a['latest_ack_registry_sha256'])
        self.assertFalse(self.paths[1].exists())

    def test_new_role_sequence_nonce_and_predecessor(self):
        a=self.guarded()
        output=Path(self.temp.name)/'mirror-next-ack.json'
        b=self.guarded(0,nonce='c'*32,sequence=2,
            previous_ack_sha256=a['acknowledgment_sha256'],
            expected_registry_head=a['latest_ack_registry_sha256'],
            output=output)
        self.assertTrue(output.exists())
        self.assertEqual(self.snapshot()['event_count'],4)
        self.assertEqual(b['acknowledgment_sha256'],
                         hashlib.sha256(output.read_bytes()).hexdigest())

    def test_reused_nonce_next_sequence_fails_before_output(self):
        a=self.guarded()
        next_path=Path(self.temp.name)/'second-attempt.json'
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(0,sequence=2,previous_ack_sha256=a['acknowledgment_sha256'],
                output=next_path,expected_registry_head=a['latest_ack_registry_sha256'])
        self.assertFalse(next_path.exists())

    def test_wrong_next_sequence_rejected(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(sequence=2)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_predecessor_sha_rejected(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(previous_ack_sha256='e'*64)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_expected_registry_head_rejected(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(expected_registry_head='f'*64)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_unknown_storage_id_rejected(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(storage_id='not-the-enrolled-storage')
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_operator_identity_refused_before_reserve(self):
        with self.assertRaises(guard.MirrorGuardConflict):
            self.guarded(operator_id='not-enrolled-operator')
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_operator_public_pem_refused(self):
        with self.assertRaises((ValueError,guard.MirrorGuardConflict,cas.CheckpointCASConflict)):
            self.guarded(signing_public=self.observers[1][1],
                         signing_public_pin=self.observers[1][2])
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_head_mirror_refused_without_nonce_consumption(self):
        with self.assertRaises((ValueError,guard.MirrorGuardConflict,cross.LedgerDivergence)):
            self.guarded(head_b='f'*64)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_bad_signed_manifest_pin_refused_before_reserve(self):
        envelopes={r:list(v) for r,v in self.complete.items()}
        raw,_=envelopes['operator-a'][0]
        envelopes['operator-a']=[(raw,'f'*64)]
        with self.assertRaises((ValueError,guard.MirrorGuardConflict,binding.SignedLedgerConflict)):
            self.guarded(signed_envelopes=envelopes)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_missing_ack_ledger_cannot_silently_reinitialize(self):
        self.ack_registry.unlink()
        with self.assertRaises((ValueError,OSError)):
            self.guarded()
        self.assertFalse(self.ack_registry.exists())

    def test_wrong_private_key_burns_nonce_with_pending_state(self):
        with self.assertRaises((ValueError,OSError,cas.CheckpointCASConflict)):
            self.guarded(signing_private=self.observers[1][0])
        pending=self.snapshot()
        self.assertEqual(pending['pending_operator_roles'],['operator-a'])
        self.assertEqual(pending['event_count'],1)
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(expected_registry_head=pending['latest_ledger_sha256'])
        self.assertEqual(self.snapshot()['event_count'],1)

    def test_nonexistent_private_key_burns_nonce(self):
        with self.assertRaises((ValueError,OSError,cas.CheckpointCASConflict)):
            self.guarded(signing_private=Path(self.temp.name)/'absent-private.pem')
        self.assertEqual(self.snapshot()['pending_operator_roles'],['operator-a'])

    def test_existing_output_fails_without_overwrite_and_leaves_pending(self):
        self.paths[0].write_text('preexisting private payload')
        self.paths[0].chmod(0o600)
        with self.assertRaises((ValueError,FileExistsError,OSError)):
            self.guarded()
        self.assertEqual(self.paths[0].read_text(),'preexisting private payload')
        self.assertEqual(self.snapshot()['pending_operator_roles'],['operator-a'])

    def test_bad_nonce_rejected_before_reservation(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.guarded(nonce='invalid')
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_body_commitment_includes_audit_id(self):
        original=self.expected_ack_body(0)
        altered=dict(original,audit_id='another-audit')
        self.assertNotEqual(guard.commitment(original),guard.commitment(altered))

    def test_body_commitment_includes_both_heads(self):
        original=self.expected_ack_body(0)
        altered=dict(original,secondary_head_sha256='f'*64)
        self.assertNotEqual(guard.commitment(original),guard.commitment(altered))

    def test_body_commitment_forbids_unknown_signed_field(self):
        original=self.expected_ack_body(0)
        with self.assertRaises(guard.MirrorGuardConflict):
            guard.commitment(dict(original,untrusted='value'))

    def test_tampered_registry_fails_closed(self):
        initial=self.guarded()
        with sqlite3.connect(self.ack_registry) as con:
            con.execute('UPDATE events SET nonce=? WHERE event_id=1',('f'*32,))
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(output=Path(self.temp.name)/'new-ack.json',
                nonce='c'*32,sequence=2,
                previous_ack_sha256=initial['acknowledgment_sha256'],
                expected_registry_head=initial['latest_ack_registry_sha256'])

    def test_atomic_competing_requests_only_one_succeeds(self):
        def race(n):
            try:
                return self.guarded(output=Path(self.temp.name)/(f'race-{n}.json'))
            except (ledger.NonceLedgerConflict,sqlite3.DatabaseError):
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            got=list(pool.map(race,(0,1)))
        self.assertEqual(sum(v is not None for v in got),1)
        self.assertEqual(self.snapshot()['event_count'],2)

    def test_disclaimer_flags_never_claim_external_custody(self):
        out=self.guarded()
        for field in ('separately_retained_registry_head_proved',
            'globally_monotonic_cross_host_nonce_cas_proved',
            'independent_physical_operator_custody_proved',
            'automatic_pending_recovery_authorized',
            'automatic_register_sync_authorized',
            'automatic_cas_retry_authorized',
            'witness_fence_retirement_authorized',
            'witness_fence_retired',
            'native_switch_game_build_verified'):
            self.assertFalse(out[field],field)

    def cli_args(self):
        self.build_manifest()
        d=self.arguments()
        return [str(self.guard_path),str(self.mirror),
            str(self.ack_registry),str(self.paths[0]),
            '--private-signed-manifest',str(self.manifest),
            '--head-a',d['head_a'],'--head-b',d['head_b'],
            '--genesis-a',d['genesis_a'],'--genesis-b',d['genesis_b'],
            '--scope',d['scope'],'--audit-id',d['audit_id'],
            '--operator-id',d['operator_id'],'--storage-id',d['storage_id'],
            '--nonce',d['nonce'],'--role',d['role'],
            '--sequence',str(d['sequence']),
            '--previous-ack-sha256',d['previous_ack_sha256'],
            '--public-a',str(d['public_a']),'--public-b',str(d['public_b']),
            '--signing-private',str(d['signing_private']),
            '--signing-public',str(d['signing_public']),
            '--signing-public-pin',d['signing_public_pin'],
            '--expected-registry-head',d['expected_registry_head']]

    def test_cli_signs_when_trust_registry_provided(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=guard.main(self.cli_args())
        self.assertEqual(status,0,out.getvalue())
        report=json.loads(out.getvalue())
        self.assertTrue(report['nonce_reserved_before_ed25519_signature'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertEqual(self.snapshot()['event_count'],2)
        self.assertNotIn(self.nonces[0],out.getvalue())

    def test_cli_refuses_stale_head_with_no_signature(self):
        args=self.cli_args()
        args[args.index('--expected-registry-head')+1]='f'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=guard.main(args)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())[
            'guarded_mirror_acknowledgment_conflict'])
        self.assertFalse(self.paths[0].exists())

    def test_cli_requires_existing_enrolled_registry(self):
        args=self.cli_args()
        args[2]=str(Path(self.temp.name)/'not-created.db')
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=guard.main(args)
        self.assertEqual(status,1)
        self.assertFalse(self.paths[0].exists())


for name in (
    'sign','compute_pin','fetch','_advanced_keeper','certificate',
    'body','endorse','bundle','args','check','create','inspect',
    'copy_args','clone','signed_body','sign_receipt',
    'operator_args','make_fields','reserve','sign_one','kwargs',
    'crosscheck','write','create_witness','inspect_witness',
    'trusted','body_for','make_signed','checked','issue','cli',
    'advance','seal_mirror','params','check_mirror','one_complete',
    'build_manifest','expected_ack_body','signed_ack','verify'
):
    if hasattr(base.SignedMirrorAcknowledgmentTests,name):
        setattr(MirrorAcknowledgmentNonceGuardTests,name,
                getattr(base.SignedMirrorAcknowledgmentTests,name))


if __name__=='__main__':
    unittest.main()
