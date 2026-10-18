"""Stage 264O: synthetic atomic guard of fork evidence Ed25519 signing."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unittest

from tests import test_record_witness_publication_nonce_divergence_attestations as fixture
from tools import audit_record_witness_publication_nonce_divergence_attestations as attest
from tools import audit_record_witness_publication_attestation_nonce_guard as guard
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_checkpoint_cas as cas


class GuardedDivergenceAttestationTests(unittest.TestCase):
    setUpClass=fixture.TwoSignedDivergenceAttestationsTests.__dict__['setUpClass']
    tearDownClass=fixture.TwoSignedDivergenceAttestationsTests.__dict__['tearDownClass']
    sign=fixture.TwoSignedDivergenceAttestationsTests.sign
    compute_pin=fixture.TwoSignedDivergenceAttestationsTests.compute_pin
    fetch=fixture.TwoSignedDivergenceAttestationsTests.fetch
    _advanced_keeper=fixture.TwoSignedDivergenceAttestationsTests._advanced_keeper
    certificate=fixture.TwoSignedDivergenceAttestationsTests.certificate
    body=fixture.TwoSignedDivergenceAttestationsTests.body
    endorse=fixture.TwoSignedDivergenceAttestationsTests.endorse
    bundle=fixture.TwoSignedDivergenceAttestationsTests.bundle
    args=fixture.TwoSignedDivergenceAttestationsTests.args
    check=fixture.TwoSignedDivergenceAttestationsTests.check
    create=fixture.TwoSignedDivergenceAttestationsTests.create
    inspect=fixture.TwoSignedDivergenceAttestationsTests.inspect
    arguments=fixture.TwoSignedDivergenceAttestationsTests.arguments
    copy_args=fixture.TwoSignedDivergenceAttestationsTests.copy_args
    clone=fixture.TwoSignedDivergenceAttestationsTests.clone
    signed_body=fixture.TwoSignedDivergenceAttestationsTests.signed_body
    sign_receipt=fixture.TwoSignedDivergenceAttestationsTests.sign_receipt
    operator_args=fixture.TwoSignedDivergenceAttestationsTests.operator_args
    make_fields=fixture.TwoSignedDivergenceAttestationsTests.make_fields
    reserve=fixture.TwoSignedDivergenceAttestationsTests.reserve
    sign_one=fixture.TwoSignedDivergenceAttestationsTests.sign_one
    kwargs=fixture.TwoSignedDivergenceAttestationsTests.kwargs
    crosscheck=fixture.TwoSignedDivergenceAttestationsTests.crosscheck
    write=fixture.TwoSignedDivergenceAttestationsTests.write
    create_witness=fixture.TwoSignedDivergenceAttestationsTests.create_witness
    inspect_witness=fixture.TwoSignedDivergenceAttestationsTests.inspect_witness
    trusted=fixture.TwoSignedDivergenceAttestationsTests.trusted
    body_for=fixture.TwoSignedDivergenceAttestationsTests.body_for
    make_signed=fixture.TwoSignedDivergenceAttestationsTests.make_signed
    params=fixture.TwoSignedDivergenceAttestationsTests.params
    checked=fixture.TwoSignedDivergenceAttestationsTests.checked
    issue=fixture.TwoSignedDivergenceAttestationsTests.issue

    def setUp(self):
        fixture.TwoSignedDivergenceAttestationsTests.setUp(self)
        self.guard_path=Path(self.temp.name)/'separate-attestation-nonce-register.db'
        self.storages=('fork-inspection-storage-a','fork-inspection-storage-b')
        self.enrolled={
            role:{'operator_id':('fork-witness-operator-a','fork-witness-operator-b')[i],
                  'storage_id':self.storages[i],
                  'public_pin':self.observers[i][2],
                  'initial_previous_sha256':self.previous[i]}
            for i,role in enumerate(('operator-a','operator-b'))}
        self.genesis=ledger.genesis_digest(self.scope,self.enrolled)
        ledger.init(self.guard_path,scope=self.scope,enrollment=self.enrolled,
                    independent_genesis_pin=self.genesis)

    def guarded(self,i=0,**changes):
        kw=dict(role=('operator-a','operator-b')[i],
            operator_id=self.enrolled[('operator-a','operator-b')[i]]['operator_id'],
            storage_id=self.storages[i],audit_id=self.audit_id,
            nonce=self.challenge[i],sequence=1,previous_pin=self.previous[i],
            signing_private=self.observers[i][0],
            public=self.observers[i][1],public_pin=self.observers[i][2],
            output=self.receipt_paths[i],**self.trusted())
        registry_head=changes.pop('expected_registry_head',self.genesis)
        kw.update(changes)
        return guard.guarded_attest(self.witness_path,self.guard_path,
                                   expected_registry_head=registry_head,**kw)

    def cli(self,i=0,**changes):
        kw=dict(role=('operator-a','operator-b')[i],
            operator_id=self.enrolled[('operator-a','operator-b')[i]]['operator_id'],
            storage_id=self.storages[i],audit_id=self.audit_id,
            nonce=self.challenge[i],sequence=1,previous=self.previous[i],
            key=self.observers[i][0],public=self.observers[i][1],
            public_pin=self.observers[i][2],output=self.receipt_paths[i],
            registry=self.guard_path,registry_head=self.genesis)
        kw.update(changes)
        pins=self.trusted()
        args=['sign',str(self.witness_path),'--scope',pins['scope'],
              '--archive-pin',pins['archive_pin'],
              '--primary-genesis-pin',pins['genesis_a'],
              '--secondary-genesis-pin',pins['genesis_b'],
              '--primary-head-pin',pins['head_a'],
              '--secondary-head-pin',pins['head_b'],
              '--audit-id',kw['audit_id'],
              '--role',kw['role'],'--operator-id',kw['operator_id'],
              '--challenge',kw['nonce'],'--sequence',str(kw['sequence']),
              '--previous-attestation-pin',kw['previous'],
              '--signing-private',str(kw['key']),
              '--signing-public',str(kw['public']),
              '--signing-public-pin',kw['public_pin'],
              '--output',str(kw['output']),
              '--attestation-registry',str(kw['registry']),
              '--expected-registry-head',kw['registry_head'],
              '--storage-id',kw['storage_id']]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=attest.main(args)
        return status,json.loads(out.getvalue())

    def snapshot(self):
        return ledger.snapshot(self.guard_path)

    def test_guarded_sign_audit_two_events_and_exact_signed_digest(self):
        result=self.guarded()
        self.assertTrue(result['nonce_reserved_before_ed25519_signing'])
        self.assertTrue(result['signed_attestation_completed_once'])
        state=ledger.snapshot(self.guard_path,
            expected_ledger_head=result['latest_attestation_registry_sha256'])
        self.assertEqual(state['event_count'],2)
        self.assertEqual(state['completed_operator_sequences']['operator-a'],1)
        self.assertEqual(state['pending_operator_roles'],[])
        self.assertFalse(result['global_cross_host_nonce_uniqueness_proved'])

    def test_two_operators_can_sign_separately_after_head_advances(self):
        first=self.guarded()
        second=self.guarded(1,expected_registry_head=
                            first['latest_attestation_registry_sha256'])
        self.assertTrue(second['signed_attestation_completed_once'])
        self.assertEqual(self.snapshot()['event_count'],4)
        result=self.checked(raw_a=self.receipt_paths[0].read_bytes(),
            raw_b=self.receipt_paths[1].read_bytes(),
            envelope_a_pin=first['attestation_envelope_sha256'],
            envelope_b_pin=second['attestation_envelope_sha256'])
        self.assertTrue(result['both_signatures_bind_same_fully_replayed_archive'])

    def test_cli_mandatory_guard_signs_and_returns_redacted_hashes(self):
        status,result=self.cli()
        self.assertEqual(status,0,result)
        self.assertTrue(result['nonce_reserved_before_ed25519_signing'])
        self.assertFalse(result['automatic_cas_retry_authorized'])
        self.assertEqual(self.snapshot()['event_count'],2)

    def test_cli_missing_registry_fails_without_signature(self):
        status,result=self.cli(registry=Path(self.temp.name)/'absent.db')
        self.assertEqual(status,1)
        self.assertTrue(result['signed_evidence_attestation_conflict'])
        self.assertFalse(self.receipt_paths[0].exists())

    def test_cli_stale_expected_head_refuses_without_output(self):
        status,result=self.cli(registry_head='f'*64)
        self.assertEqual(status,1)
        self.assertTrue(result['signed_evidence_attestation_conflict'])
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_cli_wrong_operator_storage_refused_without_consumption(self):
        status,result=self.cli(storage_id='untrusted-storage')
        self.assertEqual(status,1)
        self.assertTrue(result['signed_evidence_attestation_conflict'])
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_cli_missing_guard_arguments_do_not_use_legacy_signing(self):
        args=['sign',str(self.witness_path),'--scope',self.scope,
              '--audit-id',self.audit_id,'--archive-pin',self.archive_pin,
              '--primary-genesis-pin',self.trust['external_primary_genesis'],
              '--secondary-genesis-pin',self.trust['external_secondary_genesis'],
              '--primary-head-pin',self.trust['external_primary_head'],
              '--secondary-head-pin',self.trust['external_secondary_head'],
              '--role','operator-a','--operator-id','fork-witness-operator-a',
              '--challenge',self.challenge[0],'--sequence','1',
              '--previous-attestation-pin',self.previous[0],
              '--signing-private',str(self.observers[0][0]),
              '--signing-public',str(self.observers[0][1]),
              '--signing-public-pin',self.observers[0][2],
              '--output',str(self.receipt_paths[0])]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=attest.main(args)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['signed_evidence_attestation_conflict'])
        self.assertFalse(self.receipt_paths[0].exists())

    def test_reused_nonce_blocked_even_with_fresh_sequence(self):
        first=self.guarded()
        output=Path(self.temp.name)/'again.json'
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(expected_registry_head=first['latest_attestation_registry_sha256'],
                output=output,sequence=2,
                previous_pin=first['attestation_envelope_sha256'])
        self.assertFalse(output.exists())
        self.assertEqual(self.snapshot()['event_count'],2)

    def test_new_nonce_and_sequence_two_allowed(self):
        first=self.guarded()
        output=Path(self.temp.name)/'next-guarded.json'
        second=self.guarded(expected_registry_head=
            first['latest_attestation_registry_sha256'],
            nonce='c'*32,sequence=2,
            previous_pin=first['attestation_envelope_sha256'],output=output)
        self.assertTrue(second['signed_attestation_completed_once'])
        self.assertEqual(self.snapshot()['event_count'],4)

    def test_wrong_prior_sha256_cannot_sign(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(previous_pin='f'*64)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_next_sequence_cannot_sign(self):
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(sequence=2)

    def test_same_nonce_across_both_operator_roles_refused(self):
        first=self.guarded()
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(1,nonce=self.challenge[0],
                expected_registry_head=first['latest_attestation_registry_sha256'])
        self.assertFalse(self.receipt_paths[1].exists())

    def test_invalid_signing_key_burns_challenge_before_attempt(self):
        with self.assertRaises((ValueError,OSError)):
            self.guarded(signing_private=self.observers[1][0])
        state=self.snapshot()
        self.assertEqual(state['pending_operator_roles'],['operator-a'])
        self.assertEqual(state['event_count'],1)
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(expected_registry_head=state['latest_ledger_sha256'])
        self.assertEqual(self.snapshot()['event_count'],1)

    def test_nonexistent_signing_private_key_is_pending_not_retried(self):
        with self.assertRaises((OSError,ValueError)):
            self.guarded(signing_private=Path(self.temp.name)/'missing-key.pem')
        self.assertEqual(self.snapshot()['pending_operator_roles'],['operator-a'])

    def test_invalid_archive_fails_before_nonce_consumption(self):
        with self.assertRaises((ValueError,OSError)):
            self.guarded(archive_pin='f'*64)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_invalid_operator_pem_refused_before_reservation(self):
        with self.assertRaises((ValueError,cas.CheckpointCASConflict)):
            self.guarded(public_pin='f'*64)
        self.assertEqual(self.snapshot()['event_count'],0)

    def test_wrong_audit_id_changes_signed_body_commitment(self):
        baseline=self.body_for(0)
        modified=dict(baseline,audit_id='other-audit')
        self.assertNotEqual(guard._commitment(baseline),guard._commitment(modified))

    def test_wrong_heads_change_signed_body_commitment(self):
        baseline=self.body_for(0)
        modified=dict(baseline,secondary_head_sha256='f'*64)
        self.assertNotEqual(guard._commitment(baseline),guard._commitment(modified))

    def test_unauthorized_extra_body_field_rejected(self):
        modified=dict(self.body_for(0),untrusted='no')
        with self.assertRaises(guard.PreSignAttestationConflict):
            guard._commitment(modified)

    def test_hash_chain_tampering_blocks_new_signature(self):
        first=self.guarded()
        with sqlite3.connect(self.guard_path) as conn:
            conn.execute('UPDATE events SET nonce=? WHERE event_id=1',('e'*32,))
        with self.assertRaises(ledger.NonceLedgerConflict):
            self.guarded(expected_registry_head=
                         first['latest_attestation_registry_sha256'],
                         nonce='c'*32,sequence=2,
                         previous_pin=first['attestation_envelope_sha256'])

    def test_missing_ledger_cannot_be_reconstructed_at_sign_time(self):
        self.guard_path.unlink()
        with self.assertRaises((ValueError,OSError)):
            self.guarded()
        self.assertFalse(self.guard_path.exists())

    def test_two_simultaneous_same_nonce_requests_sign_at_most_once(self):
        def attempt(i):
            try:
                return self.guarded(output=Path(self.temp.name)/f'race-{i}.json')
            except (ledger.NonceLedgerConflict,sqlite3.DatabaseError):
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,(0,1)))
        self.assertEqual(len([r for r in results if r is not None]),1)
        self.assertEqual(self.snapshot()['event_count'],2)

    def test_output_explicitly_disclaims_external_consensus(self):
        data=self.guarded()
        for name in ('independently_retained_attestation_pin_proved',
                     'independent_offhost_registry_head_retention_proved',
                     'global_cross_host_nonce_uniqueness_proved',
                     'automatic_pending_reservation_recovery_authorized',
                     'offhost_monotonic_attestation_cas_proved',
                     'automatic_ledger_merge_authorized',
                     'witness_fence_retirement_authorized',
                     'witness_fence_retired','native_switch_game_build_verified'):
            self.assertFalse(data[name],name)

    def test_separate_registry_enrollment_cannot_reuse_receipt_registry(self):
        other=Path(self.temp.name)/'other-registry.db'
        wrong={role:dict(e) for role,e in self.enrolled.items()}
        wrong['operator-a']['operator_id']='other-identity'
        other_genesis=ledger.genesis_digest(self.scope,wrong)
        ledger.init(other,scope=self.scope,enrollment=wrong,
                    independent_genesis_pin=other_genesis)
        with self.assertRaises(ledger.NonceLedgerConflict):
            guard.guarded_attest(self.witness_path,other,
                expected_registry_head=other_genesis,
                storage_id=self.storages[0],role='operator-a',
                operator_id=self.enrolled['operator-a']['operator_id'],
                audit_id=self.audit_id,nonce=self.challenge[0],
                sequence=1,previous_pin=self.previous[0],
                signing_private=self.observers[0][0],
                public=self.observers[0][1],public_pin=self.observers[0][2],
                output=self.receipt_paths[0],**self.trusted())


if __name__=='__main__':
    unittest.main()
