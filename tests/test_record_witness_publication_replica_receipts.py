"""Stage 264H two independently pinned Ed25519 replica inspection receipts."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_equivocation_replica as previous
from tools import audit_record_witness_publication_replica_receipts as receipts
from tools import audit_record_witness_publication_equivocation_archive as archive
from tools import audit_record_witness_publication_equivocation_replica as replica
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_witness_fence_reconciliation import _sign


class ReplicaReceiptTests(unittest.TestCase):
    setUpClass=previous.EvidenceReplicaTests.__dict__['setUpClass']
    tearDownClass=previous.EvidenceReplicaTests.__dict__['tearDownClass']
    sign=previous.EvidenceReplicaTests.sign
    compute_pin=previous.EvidenceReplicaTests.compute_pin
    fetch=previous.EvidenceReplicaTests.fetch
    _advanced_keeper=previous.EvidenceReplicaTests._advanced_keeper
    certificate=previous.EvidenceReplicaTests.certificate
    body=previous.EvidenceReplicaTests.body
    endorse=previous.EvidenceReplicaTests.endorse
    bundle=previous.EvidenceReplicaTests.bundle
    args=previous.EvidenceReplicaTests.args
    check=previous.EvidenceReplicaTests.check
    create=previous.EvidenceReplicaTests.create
    inspect=previous.EvidenceReplicaTests.inspect
    arguments=previous.EvidenceReplicaTests.arguments
    copy_args=previous.EvidenceReplicaTests.copy_args
    clone=previous.EvidenceReplicaTests.clone

    def setUp(self):
        previous.EvidenceReplicaTests.setUp(self)
        self.clone()
        self.nonces=('a'*32,'b'*32)
        self.previous_receipts=('0'*64,'1'*64)
        self.id='archive-audit-one'
        self.receipt_paths=[Path(self.temp.name)/'receipt-a.json',
                            Path(self.temp.name)/'receipt-b.json']
        self.raw=[]
        for idx in (0,1):
            self.raw.append(self.sign_receipt(idx))
        self.receipt_pins=[hashlib.sha256(x).hexdigest() for x in self.raw]

    def signed_body(self,idx,**override):
        obj=receipts._body(
            ('operator-a','operator-b')[idx],
            ('private-operator-a','private-operator-b')[idx],
            ('private-store-a','private-store-b')[idx],
            self.scope,self.id,self.nonces[idx],1,
            self.previous_receipts[idx],self.primary_pin,self.evidence_sha)
        obj.update(override)
        return obj

    def sign_receipt(self,idx,**override):
        path=Path(self.temp.name)/('synthetic-receipt-%d-%d.json'%(
            idx,len(list(Path(self.temp.name).glob('synthetic-receipt-*')))))
        _sign(self.signed_body(idx,**override),receipts.SCHEMA,receipts.DOMAIN,
              self.observers[idx][0],path)
        return path.read_bytes()

    def params(self):
        return dict(
            expected_scope=self.scope,
            expected_audit_id=self.id,
            expected_operator_a_id='private-operator-a',
            expected_operator_b_id='private-operator-b',
            expected_storage_a_id='private-store-a',
            expected_storage_b_id='private-store-b',
            challenge_a=self.nonces[0],challenge_b=self.nonces[1],
            previous_a_sha256=self.previous_receipts[0],
            previous_b_sha256=self.previous_receipts[1],
            previous_a_sequence=0,previous_b_sequence=0,
            receipt_a_public=self.observers[0][1],
            receipt_a_public_pin=self.observers[0][2],
            receipt_b_public=self.observers[1][1],
            receipt_b_public_pin=self.observers[1][2],
            receipt_a_envelope_pin=self.receipt_pins[0],
            receipt_b_envelope_pin=self.receipt_pins[1],
            primary_pin=self.primary_pin,secondary_pin=self.primary_pin,
            evidence_pin=self.evidence_sha,
            evidence_operator_a_public=self.observers[0][1],
            evidence_operator_a_pin=self.observers[0][2],
            evidence_operator_b_public=self.observers[1][1],
            evidence_operator_b_pin=self.observers[1][2],
        )

    def verify(self,*,raw_a=None,raw_b=None,**changed):
        kw=self.params()
        kw.update(changed)
        return receipts.verify(
            self.archive,self.secondary,
            self.raw[0] if raw_a is None else raw_a,
            self.raw[1] if raw_b is None else raw_b,
            **kw)

    def attest(self,idx,**changed):
        arg=dict(
            role=('operator-a','operator-b')[idx],
            operator_id=('private-operator-a','private-operator-b')[idx],
            storage_id=('private-store-a','private-store-b')[idx],
            scope=self.scope,audit_id=self.id,
            nonce=self.nonces[idx],receipt_sequence=1,
            previous_receipt_sha256=self.previous_receipts[idx],
            independent_archive_pin=self.primary_pin,
            independent_evidence_pin=self.evidence_sha,
            evidence_operator_a_public=self.observers[0][1],
            evidence_operator_a_pin=self.observers[0][2],
            evidence_operator_b_public=self.observers[1][1],
            evidence_operator_b_pin=self.observers[1][2],
            receipt_signing_private=self.observers[idx][0],
            receipt_public=self.observers[idx][1],
            receipt_public_pin=self.observers[idx][2],
            output=self.receipt_paths[idx],
        )
        arg.update(changed)
        return receipts.attest(
            self.archive if idx==0 else self.secondary,**arg)

    def test_two_signed_roles_confirm_pinned_archived_evidence(self):
        result=self.verify()
        self.assertTrue(result['two_distinct_pinned_ed25519_receipt_operators_verified'])
        self.assertTrue(result['both_receipts_bind_exact_archive_and_evidence_sha256'])
        self.assertTrue(result['two_local_archives_reverified_around_receipts'])
        self.assertFalse(result['external_operator_independence_proved'])
        self.assertFalse(result['witness_fence_retired'])

    def test_attest_actual_audited_copy_only(self):
        a=self.attest(0)
        b=self.attest(1)
        self.assertTrue(a['signed_local_inspection_revalidated'])
        self.assertTrue(b['signed_local_inspection_revalidated'])
        self.assertEqual(a['receipt_envelope_sha256'],
                         hashlib.sha256(self.receipt_paths[0].read_bytes()).hexdigest())
        self.assertEqual(b['receipt_envelope_sha256'],
                         hashlib.sha256(self.receipt_paths[1].read_bytes()).hexdigest())
        self.assertTrue(self.verify(raw_a=self.receipt_paths[0].read_bytes(),
            raw_b=self.receipt_paths[1].read_bytes(),
            receipt_a_envelope_pin=a['receipt_envelope_sha256'],
            receipt_b_envelope_pin=b['receipt_envelope_sha256'])[
                'both_receipt_sequences_strictly_advance'])

    def test_attest_receipt_never_overwrites_existing(self):
        original=self.attest(0)
        unchanged=self.receipt_paths[0].read_bytes()
        with self.assertRaises(FileExistsError):
            self.attest(0)
        self.assertEqual(self.receipt_paths[0].read_bytes(),unchanged)
        self.assertEqual(original['receipt_envelope_sha256'],
                         hashlib.sha256(unchanged).hexdigest())

    def test_attest_wrong_archive_scope_refused_before_signing(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.attest(0,scope='wrong-scope')
        self.assertFalse(self.receipt_paths[0].exists())

    def test_attest_wrong_external_archive_pin_refused(self):
        with self.assertRaises((archive.EvidenceArchiveConflict,
                                replica.DualCopyConflict)):
            self.attest(0,independent_archive_pin='f'*64)
        self.assertFalse(self.receipt_paths[0].exists())

    def test_attest_missing_copy_refused(self):
        self.secondary.unlink()
        with self.assertRaises((ValueError,OSError)):
            self.attest(1)
        self.assertFalse(self.receipt_paths[1].exists())

    def test_audit_id_changed_is_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(expected_audit_id='wrong-audit-id')

    def test_challenge_replay_different_nonce_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(challenge_a='c'*32)

    def test_duplicate_challenges_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(challenge_b=self.nonces[0])

    def test_invalid_challenge_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(challenge_b='not-a-nonce')

    def test_same_storage_identifier_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(expected_storage_b_id='private-store-a')

    def test_same_operator_identifier_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(expected_operator_b_id='private-operator-a')

    def test_same_ed25519_der_public_key_refused(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(receipt_b_public=self.observers[0][1],
                        receipt_b_public_pin=self.observers[0][2])

    def test_wrong_operator_public_pem_pin_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(receipt_a_public_pin='f'*64)

    def test_wrong_archive_sha256_rejected(self):
        with self.assertRaises((replica.DualCopyConflict,archive.EvidenceArchiveConflict)):
            self.verify(primary_pin='f'*64)

    def test_wrong_evidence_sha256_rejected(self):
        with self.assertRaises((replica.DualCopyConflict,archive.EvidenceArchiveConflict)):
            self.verify(evidence_pin='f'*64)

    def test_wrong_external_envelope_pin_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(receipt_b_envelope_pin='f'*64)

    def test_previous_receipt_digest_substitution_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(previous_a_sha256='f'*64)

    def test_previous_sequence_replay_rejected(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(previous_b_sequence=1)

    def test_boolean_sequence_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.verify(previous_a_sequence=True)

    def test_wrong_operator_role_inside_valid_signature_refused(self):
        forged=self.sign_receipt(1,operator_role='operator-a')
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(raw_b=forged,receipt_b_envelope_pin=
                        hashlib.sha256(forged).hexdigest())

    def test_wrong_signed_archive_sha256_refused(self):
        forged=self.sign_receipt(0,archive_sha256='f'*64)
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(raw_a=forged,receipt_a_envelope_pin=
                        hashlib.sha256(forged).hexdigest())

    def test_forged_release_flag_refused(self):
        forged=self.sign_receipt(0,witness_fence_retirement_authorized=True)
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(raw_a=forged,receipt_a_envelope_pin=
                        hashlib.sha256(forged).hexdigest())

    def test_swapped_valid_receipts_refused(self):
        with self.assertRaises(receipts.ReceiptConflict):
            self.verify(raw_a=self.raw[1],raw_b=self.raw[0],
                        receipt_a_envelope_pin=self.receipt_pins[1],
                        receipt_b_envelope_pin=self.receipt_pins[0])

    def test_missing_secondary_archive_refused(self):
        self.secondary.unlink()
        with self.assertRaises((ValueError,OSError,replica.DualCopyConflict)):
            self.verify()

    def test_modified_archive_refused_even_with_signed_receipts(self):
        self.secondary.write_bytes(b'changed')
        with self.assertRaises((ValueError,OSError,replica.DualCopyConflict)):
            self.verify()

    def test_no_false_external_custody_or_fork_claims(self):
        observed=self.verify()
        for field in (
            'external_operator_independence_proved',
            'external_challenge_freshness_proved',
            'physical_durability_proved',
            'externally_retained_latest_receipt_pins_proved',
            'no_concurrent_receipt_fork_proved',
            'witness_fence_retirement_authorized',
            'witness_fence_retired',
            'automatic_cas_retry_authorized',
            'native_switch_game_build_verified'):
            self.assertFalse(observed[field])

    def test_cli_redacted_conflict_when_receipt_missing(self):
        f=Path(self.temp.name)/'valid-a.json'
        f.write_bytes(self.raw[0])
        f.chmod(0o600)
        argv=['verify',str(self.archive),str(self.secondary),
            '--receipt-a',str(f),
            '--receipt-b',str(Path(self.temp.name)/'missing-b.json'),
            '--scope',self.scope,'--audit-id',self.id,
            '--primary-pin',self.primary_pin,'--secondary-pin',self.primary_pin,
            '--evidence-pin',self.evidence_sha,
        ]
        for idx,letter in enumerate(('a','b')):
            argv.extend([
                '--operator-'+letter+'-id',
                 ('private-operator-a','private-operator-b')[idx],
                '--storage-'+letter+'-id',
                 ('private-store-a','private-store-b')[idx],
                '--challenge-'+letter,self.nonces[idx],
                '--previous-'+letter+'-sha256',self.previous_receipts[idx],
                '--previous-'+letter+'-sequence','0',
                '--receipt-'+letter+'-public',str(self.observers[idx][1]),
                '--receipt-'+letter+'-public-pin',self.observers[idx][2],
                '--receipt-'+letter+'-envelope-pin',self.receipt_pins[idx],
                '--evidence-operator-'+letter+'-public',
                 str(self.observers[idx][1]),
                '--evidence-operator-'+letter+'-pin',self.observers[idx][2]])
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=receipts.main(argv)
        self.assertEqual(status,1)
        obj=json.loads(out.getvalue())
        self.assertTrue(obj['receipt_conflict'])
        self.assertFalse(obj['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__=='__main__':
    unittest.main()
