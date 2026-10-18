"""Stage 264Q: two externally signed acknowledgments of complete mirror audit."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_attestation_registry_binding as prior
from tools import audit_record_witness_publication_signed_mirror_acknowledgments as q
from tools import audit_record_witness_publication_attestation_registry_binding as bound
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_witness_fence_reconciliation import _sign


class SignedMirrorAcknowledgmentTests(unittest.TestCase):
    setUpClass=prior.MirroredAttestationBindingTests.__dict__['setUpClass']
    tearDownClass=prior.MirroredAttestationBindingTests.__dict__['tearDownClass']

    def setUp(self):
        prior.MirroredAttestationBindingTests.setUp(self)
        self.advance()
        self.advance(1)
        self.seal_mirror()
        self.audit_id='mirror-reviewed-2026'
        self.nonces=('a'*32,'b'*32)
        self.previous=('a'*64,'b'*64)
        self.paths=[Path(self.temp.name)/'mirror-sign-a.json',
                    Path(self.temp.name)/'mirror-sign-b.json']
        self.acks=[self.signed_ack(0),self.signed_ack(1)]
        self.pins=[hashlib.sha256(raw).hexdigest() for raw in self.acks]

    def expected(self,i,**changes):
        p=self.params()
        audited=bound.verify(self.guard_path,self.mirror,**p)
        data=q.expected_body(audited,scope=self.scope,audit_id=self.audit_id,
            operator_role=('operator-a','operator-b')[i],
            operator_id=('fork-witness-operator-a','fork-witness-operator-b')[i],
            challenge=self.nonces[i],sequence=1,
            previous_sha256=self.previous[i],
            genesis_a=self.genesis,genesis_b=self.genesis,
            head_a=p['primary_head_pin'],head_b=p['secondary_head_pin'],
            manifest_sha256=q.manifest_digest(self.complete))
        data.update(changes)
        return data

    def signed_ack(self,i,**changes):
        path=Path(self.temp.name)/('ack-temp-%s-%d.json'%(
            i,len(list(Path(self.temp.name).glob('ack-temp-*')))))
        _sign(self.expected(i,**changes),q.SCHEMA,q.DOMAIN,
              self.observers[i][0],path)
        return path.read_bytes()

    def verify(self,**changes):
        p=self.params()
        opts=dict(scope=self.scope,audit_id=self.audit_id,
            head_a=p['primary_head_pin'],head_b=p['secondary_head_pin'],
            genesis_a=self.genesis,genesis_b=self.genesis,
            operator_a_id='fork-witness-operator-a',
            operator_b_id='fork-witness-operator-b',
            public_a=self.observers[0][1],public_b=self.observers[1][1],
            nonce_a=self.nonces[0],nonce_b=self.nonces[1],
            sequence_a=1,sequence_b=1,
            previous_a=self.previous[0],previous_b=self.previous[1],
            ack_a_pin=self.pins[0],ack_b_pin=self.pins[1],
            signed_envelopes=self.complete)
        signed_a=changes.pop('signed_a',self.acks[0])
        signed_b=changes.pop('signed_b',self.acks[1])
        opts.update(changes)
        return q.verify(self.guard_path,self.mirror,signed_a,signed_b,**opts)

    def test_two_real_signed_operator_claims_verify(self):
        result=self.verify()
        self.assertTrue(result['two_independently_sha256_pinned_ed25519_mirror_receipts_verified'])
        self.assertTrue(result['all_registered_signed_completions_reverified'])
        self.assertEqual(result['verified_signed_completion_count'],2)
        self.assertFalse(result['witness_fence_retired'])

    def test_same_enrolled_manifest_digest_is_deterministic(self):
        a=q.manifest_digest(self.complete)
        b=q.manifest_digest({'operator-b':list(self.complete['operator-b']),
                             'operator-a':list(self.complete['operator-a'])})
        self.assertEqual(a,b)
        self.assertEqual(a,self.verify()['exact_signed_completion_manifest_sha256'])

    def test_signed_manifests_with_extra_envelope_rejected(self):
        wrong={role:list(items) for role,items in self.complete.items()}
        wrong['operator-a'].append(wrong['operator-a'][0])
        with self.assertRaises(bound.SignedLedgerConflict):
            self.verify(signed_envelopes=wrong)

    def test_missing_signed_completion_in_manifest_rejected(self):
        with self.assertRaises(bound.SignedLedgerConflict):
            self.verify(signed_envelopes={'operator-a':[], 'operator-b':self.complete['operator-b']})

    def test_wrong_manifest_pin_rejected(self):
        wrong={role:list(items) for role,items in self.complete.items()}
        raw,_=wrong['operator-a'][0]
        wrong['operator-a']=[(raw,'f'*64)]
        with self.assertRaises((q.SignedMirrorConflict,bound.SignedLedgerConflict)):
            self.verify(signed_envelopes=wrong)

    def test_forked_registry_copy_is_not_accepted(self):
        # Identity stays distinct but contents no longer match source.
        from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
        head=ledger.snapshot(self.mirror)['latest_ledger_sha256']
        ledger._record(self.mirror,action='reserve',
            expected_head=head,scope=self.scope,role='operator-a',
            operator_id=self.enrolled['operator-a']['operator_id'],
            storage_id=self.storages[0],
            operator_public_pin=self.observers[0][2],
            nonce='e'*32,seq=2,previous=self.complete['operator-a'][0][1],
            archive_pin=self.archive_pin,evidence_pin='f'*64)
        with self.assertRaises((ValueError,bound.SignedLedgerConflict,cross.LedgerDivergence,cas.CheckpointCASConflict)):
            self.verify()

    def test_wrong_enrolled_public_key_rejected(self):
        with self.assertRaises((ValueError,bound.SignedLedgerConflict,cross.LedgerDivergence,cas.CheckpointCASConflict)):
            self.verify(public_b=self.observers[0][1])

    def test_duplicate_enrolled_operator_id_rejected(self):
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(operator_b_id='fork-witness-operator-a')

    def test_signed_but_unenrolled_operator_identity_rejected(self):
        forged=self.signed_ack(0,operator_id='independent-looking-unenrolled-id')
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(signed_a=forged,
                ack_a_pin=hashlib.sha256(forged).hexdigest(),
                operator_a_id='independent-looking-unenrolled-id')

    def test_duplicate_challenges_rejected(self):
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(nonce_b=self.nonces[0])

    def test_wrong_expected_nonce_rejected(self):
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(nonce_b='c'*32)

    def test_invalid_nonce_type_rejected(self):
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(nonce_a='bad')

    def test_wrong_acknowledgment_sequence_rejected(self):
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(sequence_a=2)

    def test_wrong_predecessor_sha_rejected(self):
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(previous_b='f'*64)

    def test_wrong_separately_pinned_envelope_sha_rejected(self):
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(ack_a_pin='f'*64)

    def test_role_a_receipt_cannot_impersonate_role_b(self):
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(signed_b=self.acks[0],ack_b_pin=self.pins[0])

    def test_wrong_head_pin_rejected(self):
        with self.assertRaises((ValueError,bound.SignedLedgerConflict,cross.LedgerDivergence,cas.CheckpointCASConflict)):
            self.verify(head_b='f'*64)

    def test_wrong_scope_rejected(self):
        with self.assertRaises((ValueError,bound.SignedLedgerConflict,cross.LedgerDivergence,cas.CheckpointCASConflict)):
            self.verify(scope='untrusted-scope')

    def test_signed_unapproved_release_flag_rejected(self):
        raw=self.signed_ack(0,witness_fence_retirement_authorized=True)
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(signed_a=raw,ack_a_pin=hashlib.sha256(raw).hexdigest())

    def test_signed_forged_offhost_custody_flag_rejected(self):
        raw=self.signed_ack(1,independent_offhost_custody_proved=True)
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(signed_b=raw,ack_b_pin=hashlib.sha256(raw).hexdigest())

    def test_signed_fake_verified_count_rejected(self):
        raw=self.signed_ack(0,verified_signed_completion_count=100)
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(signed_a=raw,ack_a_pin=hashlib.sha256(raw).hexdigest())

    def test_signed_wrong_manifest_digest_rejected(self):
        raw=self.signed_ack(1,exact_signed_completion_manifest_sha256='f'*64)
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(signed_b=raw,ack_b_pin=hashlib.sha256(raw).hexdigest())

    def test_signed_unknown_extra_field_rejected(self):
        raw=self.signed_ack(1,unexpected='invalid')
        with self.assertRaises(q.SignedMirrorConflict):
            self.verify(signed_b=raw,ack_b_pin=hashlib.sha256(raw).hexdigest())

    def test_duplicate_acknowledgment_body_does_not_create_quorum(self):
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(signed_b=self.acks[0],ack_b_pin=self.pins[0])

    def test_unauthenticated_raw_json_rejected(self):
        raw=b'{"schema":"forged"}'
        with self.assertRaises((ValueError,q.SignedMirrorConflict,cas.CheckpointCASConflict)):
            self.verify(signed_a=raw,ack_a_pin=hashlib.sha256(raw).hexdigest())

    def test_reports_are_explicitly_not_external_custody_proof(self):
        result=self.verify()
        for field in ('independent_offhost_signers_proved',
                      'external_receipt_pin_retention_proved',
                      'globally_unique_challenge_cas_proved',
                      'both_signatures_made_after_actual_live_inspection_proved',
                      'automatic_register_sync_authorized',
                      'automatic_cas_retry_authorized',
                      'witness_fence_retirement_authorized',
                      'witness_fence_retired',
                      'native_switch_game_build_verified'):
            self.assertFalse(result[field],field)

    def cli_args(self):
        self.build_manifest()
        args=[str(self.guard_path),str(self.mirror),
              '--scope',self.scope,'--audit-id',self.audit_id,
              '--genesis-a',self.genesis,'--genesis-b',self.genesis]
        head=self.params()['primary_head_pin']
        args+=['--head-a',head,'--head-b',head,
               '--private-signed-manifest',str(self.manifest)]
        for i,role in enumerate(('a','b')):
            path=self.paths[i]
            path.write_bytes(self.acks[i])
            path.chmod(0o600)
            args.extend([
                '--ack-'+role,str(path),
                '--ack-'+role+'-pin',self.pins[i],
                '--public-'+role,str(self.observers[i][1]),
                '--operator-'+role+'-id','fork-witness-operator-'+role,
                '--nonce-'+role,self.nonces[i],
                '--sequence-'+role,'1',
                '--previous-'+role+'-sha256',self.previous[i]])
        return args

    def test_cli_redacted_verifier_success(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=q.main(self.cli_args())
        self.assertEqual(status,0,out.getvalue())
        result=json.loads(out.getvalue())
        self.assertTrue(result['both_signatures_bind_same_reaudited_full_mirror'])
        self.assertNotIn(self.nonces[0],out.getvalue())
        self.assertNotIn('signature_hex',out.getvalue())

    def test_cli_missing_ack_fails_closed_without_recovery(self):
        args=self.cli_args()
        args[args.index('--ack-b')+1]=str(Path(self.temp.name)/'missing.json')
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=q.main(args)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['signed_mirror_audit_conflict'])
        self.assertFalse(json.loads(out.getvalue())['witness_fence_retired'])

    def test_cli_wrong_external_pin_fails_closed(self):
        args=self.cli_args()
        args[args.index('--ack-a-pin')+1]='f'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=q.main(args)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['signed_mirror_audit_conflict'])


for name in (
    'sign','compute_pin','fetch','_advanced_keeper','certificate','body',
    'endorse','bundle','args','check','create','inspect','arguments','copy_args',
    'clone','signed_body','sign_receipt','operator_args','make_fields','reserve',
    'sign_one','kwargs','crosscheck','write','create_witness','inspect_witness',
    'trusted','body_for','make_signed','checked','issue','guarded','cli','snapshot',
    'advance','seal_mirror','params','check_mirror','one_complete','build_manifest'
):
    if hasattr(prior.MirroredAttestationBindingTests,name):
        setattr(SignedMirrorAcknowledgmentTests,name,
                getattr(prior.MirroredAttestationBindingTests,name))

if __name__=='__main__':
    unittest.main()
