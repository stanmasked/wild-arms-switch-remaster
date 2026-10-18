"""Stage 264I signed receipt equivocation and nonce-reuse regressions."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_replica_receipts as prior
from tools import audit_record_witness_publication_receipt_challenge_conflict as conflict
from tools import audit_record_witness_publication_checkpoint_cas as cas


class ReceiptChallengeConflictTests(unittest.TestCase):
    setUpClass=prior.ReplicaReceiptTests.__dict__['setUpClass']
    tearDownClass=prior.ReplicaReceiptTests.__dict__['tearDownClass']
    sign=prior.ReplicaReceiptTests.sign
    compute_pin=prior.ReplicaReceiptTests.compute_pin
    fetch=prior.ReplicaReceiptTests.fetch
    _advanced_keeper=prior.ReplicaReceiptTests._advanced_keeper
    certificate=prior.ReplicaReceiptTests.certificate
    body=prior.ReplicaReceiptTests.body
    endorse=prior.ReplicaReceiptTests.endorse
    bundle=prior.ReplicaReceiptTests.bundle
    args=prior.ReplicaReceiptTests.args
    check=prior.ReplicaReceiptTests.check
    create=prior.ReplicaReceiptTests.create
    inspect=prior.ReplicaReceiptTests.inspect
    arguments=prior.ReplicaReceiptTests.arguments
    copy_args=prior.ReplicaReceiptTests.copy_args
    clone=prior.ReplicaReceiptTests.clone
    signed_body=prior.ReplicaReceiptTests.signed_body
    sign_receipt=prior.ReplicaReceiptTests.sign_receipt
    params=prior.ReplicaReceiptTests.params
    verify=prior.ReplicaReceiptTests.verify
    attest=prior.ReplicaReceiptTests.attest

    def setUp(self):
        prior.ReplicaReceiptTests.setUp(self)
        self.first=self.raw[0]
        self.second=self.sign_receipt(0,archive_sha256='f'*64)
        self.first_pin=hashlib.sha256(self.first).hexdigest()
        self.second_pin=hashlib.sha256(self.second).hexdigest()

    def inputs(self):
        return dict(
            scope=self.scope,role='operator-a',
            operator_id='private-operator-a',
            nonce=self.nonces[0],
            operator_public=self.observers[0][1],
            operator_public_pin=self.observers[0][2],
            first_envelope_pin=self.first_pin,
            second_envelope_pin=self.second_pin,
            first_audit_id=self.id,second_audit_id=self.id,
            first_sequence=1,second_sequence=1,
            first_previous_sha256=self.previous_receipts[0],
            second_previous_sha256=self.previous_receipts[0],
        )

    def evaluate(self,*,first=None,second=None,**change):
        kw=self.inputs()
        kw.update(change)
        return conflict.verify(self.first if first is None else first,
            self.second if second is None else second,**kw)

    def test_two_genuine_signed_conflicting_archive_claims_detected(self):
        result=self.evaluate()
        self.assertTrue(result['conflicting_same_predecessor_claims_detected'])
        self.assertFalse(result['reused_nonce_across_distinct_receipt_contexts_detected'])
        self.assertEqual(result['incident_type'],'conflicting_same_predecessor_claims')
        self.assertFalse(result['actual_archive_custody_proved'])
        self.assertFalse(result['witness_fence_retired'])

    def test_different_signed_storage_claim_is_material_conflict(self):
        second=self.sign_receipt(0,storage_id='alternate-store')
        result=self.evaluate(second=second,
            second_envelope_pin=hashlib.sha256(second).hexdigest())
        self.assertTrue(result['conflicting_same_predecessor_claims_detected'])

    def test_different_signed_evidence_claim_is_material_conflict(self):
        second=self.sign_receipt(0,canonical_evidence_sha256='a'*64)
        result=self.evaluate(second=second,
            second_envelope_pin=hashlib.sha256(second).hexdigest())
        self.assertTrue(result['conflicting_same_predecessor_claims_detected'])

    def test_same_nonce_two_different_audits_detected(self):
        second=self.sign_receipt(0,audit_id='second-audit')
        result=self.evaluate(second=second,second_audit_id='second-audit',
            second_envelope_pin=hashlib.sha256(second).hexdigest())
        self.assertTrue(result['reused_nonce_across_distinct_receipt_contexts_detected'])
        self.assertFalse(result['conflicting_same_predecessor_claims_detected'])

    def test_nonce_reused_at_next_sequence_detected(self):
        second=self.sign_receipt(0,receipt_sequence=2,
            previous_receipt_sha256=self.first_pin)
        result=self.evaluate(second=second,second_sequence=2,
            second_previous_sha256=self.first_pin,
            second_envelope_pin=hashlib.sha256(second).hexdigest())
        self.assertEqual(result['incident_type'],'cross_context_nonce_reuse')

    def test_nonce_reused_with_different_predecessor_detected(self):
        second=self.sign_receipt(0,previous_receipt_sha256='d'*64)
        result=self.evaluate(second=second,second_previous_sha256='d'*64,
            second_envelope_pin=hashlib.sha256(second).hexdigest())
        self.assertTrue(result['reused_nonce_across_distinct_receipt_contexts_detected'])

    def test_swap_order_keeps_canonical_incident_digest(self):
        original=self.evaluate()
        swapped=self.evaluate(first=self.second,second=self.first,
            first_envelope_pin=self.second_pin,
            second_envelope_pin=self.first_pin)
        self.assertEqual(original['canonical_incident_sha256'],
                         swapped['canonical_incident_sha256'])

    def test_exact_independently_pinned_incident_accepted(self):
        sha=self.evaluate()['canonical_incident_sha256']
        self.assertEqual(self.evaluate(expected_incident_sha256=sha)[
            'canonical_incident_sha256'],sha)

    def test_changed_independent_incident_pin_rejected(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(expected_incident_sha256='c'*64)

    def test_identical_receipt_is_not_proof_of_two_issuances(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second=self.first,second_envelope_pin=self.first_pin)

    def test_wrong_first_envelope_pin_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(first_envelope_pin='c'*64)

    def test_wrong_second_envelope_pin_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second_envelope_pin='c'*64)

    def test_swapped_envelope_pins_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(first_envelope_pin=self.second_pin,
                          second_envelope_pin=self.first_pin)

    def test_wrong_operator_pem_pin_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.evaluate(operator_public_pin='c'*64)

    def test_unenrolled_signing_public_key_refused(self):
        with self.assertRaises(ValueError):
            self.evaluate(operator_public=self.observers[1][1],
                          operator_public_pin=self.observers[1][2])

    def test_wrong_expected_nonce_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(nonce='c'*32)

    def test_invalid_nonce_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.evaluate(nonce='wrong')

    def test_wrong_scope_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(scope='unexpected-scope')

    def test_wrong_role_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(role='operator-b')

    def test_wrong_operator_id_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(operator_id='untrusted-operator')

    def test_wrong_first_audit_id_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(first_audit_id='wrong-audit')

    def test_wrong_second_audit_id_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second_audit_id='wrong-audit')

    def test_wrong_first_sequence_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(first_sequence=2)

    def test_wrong_second_sequence_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second_sequence=2)

    def test_boolean_sequence_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(first_sequence=True)

    def test_zero_sequence_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second_sequence=0)

    def test_wrong_first_predecessor_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(first_previous_sha256='e'*64)

    def test_wrong_second_predecessor_refused(self):
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second_previous_sha256='e'*64)

    def test_signed_release_flag_true_rejected(self):
        second=self.sign_receipt(0,witness_fence_retirement_authorized=True)
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second=second,second_envelope_pin=
                          hashlib.sha256(second).hexdigest())

    def test_signed_external_custody_true_rejected(self):
        second=self.sign_receipt(0,external_physical_custody_proved=True)
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second=second,second_envelope_pin=
                          hashlib.sha256(second).hexdigest())

    def test_signed_inspection_flag_false_rejected(self):
        second=self.sign_receipt(0,copy_inspection_performed=False)
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second=second,second_envelope_pin=
                          hashlib.sha256(second).hexdigest())

    def test_extra_signed_field_rejected(self):
        second=self.sign_receipt(0,unrecognized='surprise')
        with self.assertRaises(conflict.ChallengeReuseConflict):
            self.evaluate(second=second,second_envelope_pin=
                          hashlib.sha256(second).hexdigest())

    def test_truncated_signed_json_rejected(self):
        truncated=b'{'
        with self.assertRaises(ValueError):
            self.evaluate(second=truncated,second_envelope_pin=
                          hashlib.sha256(truncated).hexdigest())

    def test_cross_operator_valid_receipt_cannot_impersonate_first(self):
        other=self.raw[1]
        with self.assertRaises(ValueError):
            self.evaluate(second=other,second_envelope_pin=
                          hashlib.sha256(other).hexdigest())

    def test_report_disclaims_nonce_registry_and_actual_archives(self):
        report=self.evaluate()
        for name in ('source_challenge_freshness_proved',
                     'actual_archive_custody_proved',
                     'either_claim_was_stored_or_committed_proved',
                     'external_nonce_uniqueness_registry_proved',
                     'honest_operator_behavior_proved',
                     'independently_retained_incident_digest_proved',
                     'witness_fence_retired',
                     'automatic_cas_retry_authorized',
                     'native_switch_game_build_verified'):
            self.assertFalse(report[name],name)

    def cli_args(self,second_path):
        first_path=Path(self.temp.name)/'first-for-conflict.json'
        first_path.write_bytes(self.first)
        first_path.chmod(0o600)
        return [
            str(first_path),str(second_path),
            '--scope',self.scope,'--role','operator-a',
            '--operator-id','private-operator-a',
            '--nonce',self.nonces[0],
            '--operator-public',str(self.observers[0][1]),
            '--operator-public-pin',self.observers[0][2],
            '--first-envelope-pin',self.first_pin,
            '--second-envelope-pin',self.second_pin,
            '--first-audit-id',self.id,
            '--second-audit-id',self.id,
            '--first-sequence','1','--second-sequence','1',
            '--first-previous-sha256',self.previous_receipts[0],
            '--second-previous-sha256',self.previous_receipts[0],
        ]

    def test_cli_success_reports_only_hashes(self):
        path=Path(self.temp.name)/'second-for-conflict.json'
        path.write_bytes(self.second)
        path.chmod(0o600)
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=conflict.main(self.cli_args(path))
        report=json.loads(out.getvalue())
        self.assertEqual(status,0,out.getvalue())
        self.assertTrue(report['conflicting_same_predecessor_claims_detected'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())

    def test_cli_missing_second_returns_redacted_failure(self):
        path=Path(self.temp.name)/'nonexistent.json'
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=conflict.main(self.cli_args(path))
        report=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertTrue(report['challenge_incident_conflict'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__=='__main__':
    unittest.main()
