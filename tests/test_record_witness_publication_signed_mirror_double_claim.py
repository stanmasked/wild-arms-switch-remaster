"""Stage 264R: two separately pinned signatures from one enrolled mirror signer."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_signed_mirror_acknowledgments as base
from tools import audit_record_witness_publication_signed_mirror_double_claim as conflict
from tools import audit_record_witness_publication_checkpoint_cas as cas


class SignedMirrorDoubleClaimTests(unittest.TestCase):
    setUpClass=base.SignedMirrorAcknowledgmentTests.__dict__['setUpClass']
    tearDownClass=base.SignedMirrorAcknowledgmentTests.__dict__['tearDownClass']

    def setUp(self):
        base.SignedMirrorAcknowledgmentTests.setUp(self)
        self.first=self.acks[0]
        self.second=self.signed_ack(0,primary_head_sha256='f'*64)
        self.first_pin=hashlib.sha256(self.first).hexdigest()
        self.second_pin=hashlib.sha256(self.second).hexdigest()

    def incident_params(self):
        return dict(scope=self.scope,role='operator-a',
            operator_id='fork-witness-operator-a',
            public=self.observers[0][1],public_pin=self.observers[0][2],
            genesis_a=self.genesis,genesis_b=self.genesis,
            first_envelope_pin=self.first_pin,second_envelope_pin=self.second_pin,
            first_audit_id=self.audit_id,second_audit_id=self.audit_id,
            first_nonce=self.nonces[0],second_nonce=self.nonces[0],
            first_sequence=1,second_sequence=1,
            first_previous_sha256=self.previous[0],
            second_previous_sha256=self.previous[0])

    def evaluate(self,*,first=None,second=None,**change):
        kw=self.incident_params()
        kw.update(change)
        return conflict.verify(self.first if first is None else first,
            self.second if second is None else second,**kw)

    def alternate(self,**changes):
        raw=self.signed_ack(0,**changes)
        return raw,hashlib.sha256(raw).hexdigest()

    def test_two_signed_same_slot_different_heads_detected(self):
        result=self.evaluate()
        self.assertTrue(result['forked_same_predecessor_mirror_acknowledgments_detected'])
        self.assertEqual(result['incident_type'],
                         'forked_same_predecessor_mirror_acknowledgments')
        self.assertFalse(result['witness_fence_retired'])

    def test_different_manifest_same_slot_detected(self):
        raw,pin=self.alternate(exact_signed_completion_manifest_sha256='e'*64)
        result=self.evaluate(second=raw,second_envelope_pin=pin)
        self.assertTrue(result['forked_same_predecessor_mirror_acknowledgments_detected'])

    def test_different_signed_audit_id_same_slot_detected(self):
        raw,pin=self.alternate(audit_id='other-mirror-audit')
        result=self.evaluate(second=raw,second_audit_id='other-mirror-audit',
                             second_envelope_pin=pin)
        self.assertTrue(result['forked_same_predecessor_mirror_acknowledgments_detected'])

    def test_different_challenge_same_slot_is_fork(self):
        raw,pin=self.alternate(challenge_nonce='c'*32)
        result=self.evaluate(second=raw,second_nonce='c'*32,
                             second_envelope_pin=pin)
        self.assertTrue(result['forked_same_predecessor_mirror_acknowledgments_detected'])

    def test_reused_nonce_in_new_sequence_detected(self):
        raw,pin=self.alternate(acknowledgment_sequence=2,
                               previous_acknowledgment_sha256=self.first_pin)
        result=self.evaluate(second=raw,second_sequence=2,
            second_previous_sha256=self.first_pin,second_envelope_pin=pin)
        self.assertTrue(result['challenge_reused_across_mirror_acknowledgment_slots_detected'])
        self.assertFalse(result['forked_same_predecessor_mirror_acknowledgments_detected'])

    def test_reused_nonce_new_predecessor_detected(self):
        raw,pin=self.alternate(previous_acknowledgment_sha256='c'*64)
        result=self.evaluate(second=raw,second_previous_sha256='c'*64,
                             second_envelope_pin=pin)
        self.assertEqual(result['incident_type'],
                         'challenge_reused_across_mirror_acknowledgment_slots')

    def test_separate_slot_fresh_nonce_is_not_double_claim(self):
        raw,pin=self.alternate(acknowledgment_sequence=2,
            previous_acknowledgment_sha256=self.first_pin,
            challenge_nonce='c'*32)
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second=raw,second_envelope_pin=pin,
                second_sequence=2,second_previous_sha256=self.first_pin,
                second_nonce='c'*32)

    def test_same_envelope_twice_is_not_second_signature(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second=self.first,second_envelope_pin=self.first_pin)

    def test_reordering_claims_preserves_incident_digest(self):
        a=self.evaluate()
        b=self.evaluate(first=self.second,second=self.first,
            first_envelope_pin=self.second_pin,second_envelope_pin=self.first_pin)
        self.assertEqual(a['canonical_incident_sha256'],b['canonical_incident_sha256'])

    def test_correct_externally_pinned_incident_digest(self):
        sha=self.evaluate()['canonical_incident_sha256']
        result=self.evaluate(expected_incident_sha256=sha)
        self.assertEqual(result['canonical_incident_sha256'],sha)

    def test_wrong_external_incident_digest_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(expected_incident_sha256='c'*64)

    def test_wrong_first_envelope_digest_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(first_envelope_pin='c'*64)

    def test_wrong_second_envelope_digest_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second_envelope_pin='c'*64)

    def test_swapped_external_envelope_pins_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(first_envelope_pin=self.second_pin,
                          second_envelope_pin=self.first_pin)

    def test_wrong_enrolled_pem_pin_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.evaluate(public_pin='c'*64)

    def test_wrong_signer_public_key_refused(self):
        with self.assertRaises((ValueError,conflict.MirrorDoubleClaimConflict)):
            self.evaluate(public=self.observers[1][1],
                          public_pin=self.observers[1][2])

    def test_other_operator_signed_receipt_is_not_same_signer(self):
        with self.assertRaises((ValueError,conflict.MirrorDoubleClaimConflict)):
            self.evaluate(second=self.acks[1],
                second_envelope_pin=hashlib.sha256(self.acks[1]).hexdigest())

    def test_wrong_expected_role_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(role='operator-b')

    def test_wrong_expected_operator_id_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(operator_id='untrusted-identity')

    def test_wrong_expected_scope_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(scope='untrusted-scope')

    def test_wrong_expected_first_audit_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(first_audit_id='wrong-audit')

    def test_wrong_expected_second_previous_sha_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second_previous_sha256='c'*64)

    def test_wrong_expected_sequence_refused(self):
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second_sequence=2)

    def test_boolean_sequence_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.evaluate(first_sequence=True)

    def test_invalid_nonce_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.evaluate(first_nonce='bad-nonce')

    def test_signed_false_offhost_custody_cannot_be_changed(self):
        raw,pin=self.alternate(independent_offhost_custody_proved=True)
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second=raw,second_envelope_pin=pin)

    def test_signed_false_fence_release_cannot_be_changed(self):
        raw,pin=self.alternate(witness_fence_retirement_authorized=True)
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second=raw,second_envelope_pin=pin)

    def test_unrecognized_signed_field_refused(self):
        raw,pin=self.alternate(unapproved_field='forged')
        with self.assertRaises(conflict.MirrorDoubleClaimConflict):
            self.evaluate(second=raw,second_envelope_pin=pin)

    def test_malformed_signed_envelope_refused(self):
        raw=b'{'
        with self.assertRaises((ValueError,conflict.MirrorDoubleClaimConflict)):
            self.evaluate(second=raw,second_envelope_pin=
                          hashlib.sha256(raw).hexdigest())

    def test_actual_sqlite_audits_are_explicitly_not_claimed(self):
        report=self.evaluate()
        for name in (
            'either_underlying_sqlite_registry_audited_proved',
            'any_attested_manifest_envelopes_were_revalidated_proved',
            'actual_independent_physical_operator_custody_proved',
            'independent_challenge_freshness_proved',
            'externally_retained_incident_digest_proved',
            'global_attestation_nonce_cas_proved',
            'automatic_register_sync_authorized',
            'automatic_cas_retry_authorized',
            'witness_fence_retirement_authorized',
            'witness_fence_retired',
            'native_switch_game_build_verified'):
            self.assertFalse(report[name],name)

    def argv(self):
        paths=[Path(self.temp.name)/'mirror-claim-first.json',
               Path(self.temp.name)/'mirror-claim-second.json']
        for path,raw in zip(paths,(self.first,self.second)):
            path.write_bytes(raw)
            path.chmod(0o600)
        return [str(paths[0]),str(paths[1]),'--scope',self.scope,
            '--role','operator-a','--operator-id','fork-witness-operator-a',
            '--public',str(self.observers[0][1]),
            '--public-pin',self.observers[0][2],
            '--genesis-a',self.genesis,'--genesis-b',self.genesis,
            '--first-envelope-pin',self.first_pin,
            '--second-envelope-pin',self.second_pin,
            '--first-audit-id',self.audit_id,
            '--second-audit-id',self.audit_id,
            '--first-nonce',self.nonces[0],
            '--second-nonce',self.nonces[0],
            '--first-sequence','1','--second-sequence','1',
            '--first-previous-sha256',self.previous[0],
            '--second-previous-sha256',self.previous[0]]

    def test_cli_valid_incident_and_redacted_output(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=conflict.main(self.argv())
        report=json.loads(out.getvalue())
        self.assertEqual(status,0,out.getvalue())
        self.assertTrue(report['forked_same_predecessor_mirror_acknowledgments_detected'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn(self.nonces[0],out.getvalue())

    def test_cli_missing_second_envelope_fail_closed(self):
        args=self.argv()
        args[1]=str(Path(self.temp.name)/'missing-second.json')
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=conflict.main(args)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['signed_mirror_double_claim_conflict'])

    def test_cli_changed_exact_sha256_refused(self):
        args=self.argv()
        args[args.index('--second-envelope-pin')+1]='f'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=conflict.main(args)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['signed_mirror_double_claim_conflict'])


for name in (
    'sign','compute_pin','fetch','_advanced_keeper','certificate','body',
    'endorse','bundle','args','check','create','inspect','arguments','copy_args',
    'clone','signed_body','sign_receipt','operator_args','make_fields','reserve',
    'sign_one','kwargs','crosscheck','write','create_witness','inspect_witness',
    'trusted','body_for','make_signed','checked','issue','guarded','cli','snapshot',
    'advance','seal_mirror','params','check_mirror','one_complete','build_manifest',
    'expected_ack_body','signed_ack'
):
    if hasattr(base.SignedMirrorAcknowledgmentTests,name):
        setattr(SignedMirrorDoubleClaimTests,name,
                getattr(base.SignedMirrorAcknowledgmentTests,name))


if __name__=='__main__':
    unittest.main()
