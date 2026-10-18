"""Stage 264N: signed fork/nonce reuse from one enrolled attestation key."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_nonce_divergence_attestations as fixture
from tools import audit_record_witness_publication_nonce_attestation_double_claim as incident
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_witness_fence_reconciliation import _sign


class DoubleAttestationClaimTests(unittest.TestCase):
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
    issue=fixture.TwoSignedDivergenceAttestationsTests.issue

    def setUp(self):
        fixture.TwoSignedDivergenceAttestationsTests.setUp(self)
        self.a=self.raw[0]
        self.b=self.make_signed(0,archive_sha256='f'*64)
        self.pin_a=hashlib.sha256(self.a).hexdigest()
        self.pin_b=hashlib.sha256(self.b).hexdigest()

    def context(self):
        return dict(
            scope=self.scope,role='operator-a',
            operator_id='fork-witness-operator-a',
            public=self.observers[0][1],public_pin=self.observers[0][2],
            first_envelope_pin=self.pin_a,second_envelope_pin=self.pin_b,
            first_audit_id=self.audit_id,second_audit_id=self.audit_id,
            first_nonce=self.challenge[0],second_nonce=self.challenge[0],
            first_sequence=1,second_sequence=1,
            first_previous_sha256=self.previous[0],
            second_previous_sha256=self.previous[0],
            first_archive_pin=self.archive_pin,second_archive_pin='f'*64,
            genesis_a=self.trust['external_primary_genesis'],
            genesis_b=self.trust['external_secondary_genesis'],
            first_head_a=self.trust['external_primary_head'],
            first_head_b=self.trust['external_secondary_head'],
            second_head_a=self.trust['external_primary_head'],
            second_head_b=self.trust['external_secondary_head'])

    def evaluate(self,*,raw_a=None,raw_b=None,**changes):
        kw=self.context()
        kw.update(changes)
        return incident.verify(self.a if raw_a is None else raw_a,
                               self.b if raw_b is None else raw_b,**kw)

    def test_signed_conflicting_same_attestation_slot_detected(self):
        x=self.evaluate()
        self.assertTrue(x['forked_same_predecessor_attestations_detected'])
        self.assertFalse(x['challenge_reused_across_attestation_slots_detected'])
        self.assertEqual(x['incident_type'],'forked_same_predecessor_attestations')
        self.assertFalse(x['witness_fence_retired'])

    def test_distinct_audit_ids_in_one_slot_are_conflicting(self):
        other=self.make_signed(0,audit_id='another-audit')
        r=self.evaluate(raw_b=other,second_audit_id='another-audit',
            second_archive_pin=self.archive_pin,
            second_envelope_pin=hashlib.sha256(other).hexdigest())
        self.assertTrue(r['forked_same_predecessor_attestations_detected'])

    def test_distinct_challenges_in_one_slot_are_conflicting(self):
        other=self.make_signed(0,challenge_nonce='c'*32)
        r=self.evaluate(raw_b=other,second_nonce='c'*32,
            second_archive_pin=self.archive_pin,
            second_envelope_pin=hashlib.sha256(other).hexdigest())
        self.assertTrue(r['forked_same_predecessor_attestations_detected'])

    def test_modified_signed_secondary_head_in_one_slot_is_conflict(self):
        other=self.make_signed(0,secondary_head_sha256='f'*64)
        r=self.evaluate(raw_b=other,
            second_archive_pin=self.archive_pin,
            second_head_b='f'*64,
            second_envelope_pin=hashlib.sha256(other).hexdigest())
        self.assertTrue(r['forked_same_predecessor_attestations_detected'])

    def test_reused_challenge_different_sequence_detected(self):
        other=self.make_signed(0,sequence=2,previous_attestation_sha256=self.pin_a)
        x=self.evaluate(raw_b=other,second_sequence=2,
            second_previous_sha256=self.pin_a,
            second_archive_pin=self.archive_pin,
            second_envelope_pin=hashlib.sha256(other).hexdigest())
        self.assertTrue(x['challenge_reused_across_attestation_slots_detected'])
        self.assertFalse(x['forked_same_predecessor_attestations_detected'])

    def test_reused_challenge_different_predecessor_detected(self):
        other=self.make_signed(0,previous_attestation_sha256='c'*64)
        x=self.evaluate(raw_b=other,second_previous_sha256='c'*64,
            second_archive_pin=self.archive_pin,
            second_envelope_pin=hashlib.sha256(other).hexdigest())
        self.assertEqual(x['incident_type'],'challenge_reused_across_attestation_slots')

    def test_fresh_challenge_and_new_slot_is_not_conflict(self):
        other=self.make_signed(0,challenge_nonce='c'*32,sequence=2,
                              previous_attestation_sha256='d'*64)
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(raw_b=other,second_nonce='c'*32,
                second_sequence=2,second_previous_sha256='d'*64,
                second_archive_pin=self.archive_pin,
                second_envelope_pin=hashlib.sha256(other).hexdigest())

    def test_same_exact_signature_does_not_prove_second_claim(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(raw_b=self.a,
                second_archive_pin=self.archive_pin,
                second_envelope_pin=self.pin_a)

    def test_swapped_order_keeps_incident_sha256(self):
        first=self.evaluate()
        swapped=self.evaluate(raw_a=self.b,raw_b=self.a,
            first_envelope_pin=self.pin_b,second_envelope_pin=self.pin_a,
            first_archive_pin='f'*64,second_archive_pin=self.archive_pin)
        self.assertEqual(first['canonical_incident_sha256'],
                         swapped['canonical_incident_sha256'])

    def test_matching_external_incident_sha256_accepted(self):
        pin=self.evaluate()['canonical_incident_sha256']
        self.assertEqual(self.evaluate(expected_incident_sha256=pin)[
            'canonical_incident_sha256'],pin)

    def test_wrong_external_incident_pin_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(expected_incident_sha256='b'*64)

    def test_wrong_second_envelope_hash_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(second_envelope_pin='c'*64)

    def test_wrong_first_envelope_hash_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(first_envelope_pin='c'*64)

    def test_swapped_exact_envelope_hashes_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(first_envelope_pin=self.pin_b,second_envelope_pin=self.pin_a)

    def test_wrong_public_key_hash_rejected(self):
        with self.assertRaises((ValueError,incident.DoubleAttestationConflict)):
            self.evaluate(public_pin='c'*64)

    def test_wrong_signer_public_key_rejected(self):
        with self.assertRaises((ValueError,incident.DoubleAttestationConflict)):
            self.evaluate(public=self.observers[1][1],
                          public_pin=self.observers[1][2])

    def test_other_operator_signature_cannot_impersonate_first(self):
        raw=self.raw[1]
        with self.assertRaises((ValueError,incident.DoubleAttestationConflict)):
            self.evaluate(raw_b=raw,second_envelope_pin=
                hashlib.sha256(raw).hexdigest())

    def test_wrong_expected_role_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(role='operator-b')

    def test_wrong_expected_operator_id_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(operator_id='another-operator')

    def test_wrong_scope_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(scope='another-scope')

    def test_wrong_signed_first_archive_pin_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(first_archive_pin='c'*64)

    def test_wrong_signed_second_archive_pin_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(second_archive_pin='c'*64)

    def test_wrong_expected_second_predecessor_rejected(self):
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(second_previous_sha256='b'*64)

    def test_invalid_sequence_boolean_rejected(self):
        with self.assertRaises((ValueError,incident.DoubleAttestationConflict)):
            self.evaluate(second_sequence=True)

    def test_invalid_nonce_rejected(self):
        with self.assertRaises((ValueError,incident.DoubleAttestationConflict)):
            self.evaluate(first_nonce='invalid-nonce')

    def test_forged_release_permission_is_rejected(self):
        forged=self.make_signed(0,witness_fence_retirement_authorized=True)
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(raw_b=forged,second_envelope_pin=
                hashlib.sha256(forged).hexdigest(),second_archive_pin=self.archive_pin)

    def test_forged_external_custody_proof_rejected(self):
        forged=self.make_signed(0,external_independent_custody_proved=True)
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(raw_b=forged,second_envelope_pin=
                hashlib.sha256(forged).hexdigest(),second_archive_pin=self.archive_pin)

    def test_forged_unknown_signed_field_rejected(self):
        forged=self.make_signed(0,unauthorized_field='surprise')
        with self.assertRaises(incident.DoubleAttestationConflict):
            self.evaluate(raw_b=forged,second_envelope_pin=
                hashlib.sha256(forged).hexdigest(),second_archive_pin=self.archive_pin)

    def test_malformed_signed_envelope_rejected(self):
        broken=b'{'
        with self.assertRaises((ValueError,incident.DoubleAttestationConflict)):
            self.evaluate(raw_b=broken,second_envelope_pin=
                hashlib.sha256(broken).hexdigest())

    def test_redacted_report_never_proves_actual_archive_inspection(self):
        output=self.evaluate()
        for f in ('either_referenced_archive_was_inspected_proved',
                  'signed_operator_honest_proved',
                  'independent_challenge_freshness_proved',
                  'externally_retained_incident_pin_proved',
                  'offhost_monotonic_attestation_cas_proved',
                  'automatic_ledger_merge_authorized',
                  'automatic_cas_retry_authorized',
                  'witness_fence_retirement_authorized',
                  'witness_fence_retired',
                  'native_switch_game_build_verified'):
            self.assertFalse(output[f],f)

    def cli_args(self):
        a=Path(self.temp.name)/'first-conflicting-attestation.json'
        b=Path(self.temp.name)/'second-conflicting-attestation.json'
        for path,raw in ((a,self.a),(b,self.b)):
            path.write_bytes(raw)
            path.chmod(0o600)
        kw=self.context()
        argv=[str(a),str(b),
            '--scope',kw['scope'],'--role',kw['role'],
            '--operator-id',kw['operator_id'],
            '--public',str(kw['public']),'--public-pin',kw['public_pin'],
            '--genesis-a',kw['genesis_a'],'--genesis-b',kw['genesis_b']]
        for prefix in ('first','second'):
            for name in ('envelope_pin','audit_id','nonce','sequence','previous_sha256',
                         'archive_pin','head_a','head_b'):
                argv+=['--'+prefix+'-'+name.replace('_','-'),str(kw[prefix+'_'+name])]
        return argv

    def test_cli_detected_incident_is_redacted(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=incident.main(self.cli_args())
        self.assertEqual(status,0,out.getvalue())
        r=json.loads(out.getvalue())
        self.assertTrue(r['forked_same_predecessor_attestations_detected'])
        self.assertFalse(r['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())
        self.assertNotIn(self.challenge[0],out.getvalue())

    def test_cli_missing_signed_envelope_fails_closed(self):
        argv=self.cli_args()
        argv[1]=str(Path(self.temp.name)/'missing-attestation.json')
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=incident.main(argv)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['attestation_double_claim_conflict'])

    def test_cli_mismatched_independent_pin_fails_closed(self):
        argv=self.cli_args()
        n=argv.index('--second-envelope-pin')
        argv[n+1]='c'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=incident.main(argv)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['attestation_double_claim_conflict'])


if __name__=='__main__':
    unittest.main()
