"""Stage 264M synthetic detached fork evidence Ed25519 operator attestations."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_receipt_nonce_divergence_evidence as fixture
from tools import audit_record_witness_publication_nonce_divergence_attestations as att
from tools import audit_record_witness_publication_receipt_nonce_divergence_evidence as evidence
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_witness_fence_reconciliation import _sign


class TwoSignedDivergenceAttestationsTests(unittest.TestCase):
    setUpClass=fixture.DetachedNonceHistoryTests.__dict__['setUpClass']
    tearDownClass=fixture.DetachedNonceHistoryTests.__dict__['tearDownClass']
    sign=fixture.DetachedNonceHistoryTests.sign
    compute_pin=fixture.DetachedNonceHistoryTests.compute_pin
    fetch=fixture.DetachedNonceHistoryTests.fetch
    _advanced_keeper=fixture.DetachedNonceHistoryTests._advanced_keeper
    certificate=fixture.DetachedNonceHistoryTests.certificate
    body=fixture.DetachedNonceHistoryTests.body
    endorse=fixture.DetachedNonceHistoryTests.endorse
    bundle=fixture.DetachedNonceHistoryTests.bundle
    args=fixture.DetachedNonceHistoryTests.args
    check=fixture.DetachedNonceHistoryTests.check
    create=fixture.DetachedNonceHistoryTests.create
    inspect=fixture.DetachedNonceHistoryTests.inspect
    arguments=fixture.DetachedNonceHistoryTests.arguments
    copy_args=fixture.DetachedNonceHistoryTests.copy_args
    clone=fixture.DetachedNonceHistoryTests.clone
    signed_body=fixture.DetachedNonceHistoryTests.signed_body
    sign_receipt=fixture.DetachedNonceHistoryTests.sign_receipt
    params=fixture.DetachedNonceHistoryTests.params
    verify=fixture.DetachedNonceHistoryTests.verify
    attest=fixture.DetachedNonceHistoryTests.attest
    operator_args=fixture.DetachedNonceHistoryTests.operator_args
    make_fields=fixture.DetachedNonceHistoryTests.make_fields
    reserve=fixture.DetachedNonceHistoryTests.reserve
    sign_one=fixture.DetachedNonceHistoryTests.sign_one
    kwargs=fixture.DetachedNonceHistoryTests.kwargs
    crosscheck=fixture.DetachedNonceHistoryTests.crosscheck
    write=fixture.DetachedNonceHistoryTests.write
    create_witness=fixture.DetachedNonceHistoryTests.create_witness
    inspect_witness=fixture.DetachedNonceHistoryTests.inspect_witness

    def setUp(self):
        fixture.DetachedNonceHistoryTests.setUp(self)
        saved=self.create_witness()
        self.archive_pin=saved['archive_sha256']
        self.audit_id='fork-evidence-audit-one'
        self.challenge=('a'*32,'b'*32)
        self.previous=('1'*64,'2'*64)
        self.receipt_paths=[Path(self.temp.name)/'signed-fork-a.json',
                            Path(self.temp.name)/'signed-fork-b.json']
        self.raw=[self.make_signed(0),self.make_signed(1)]
        self.pins=[hashlib.sha256(v).hexdigest() for v in self.raw]

    def trusted(self):
        return dict(
            scope=self.scope,archive_pin=self.archive_pin,
            genesis_a=self.trust['external_primary_genesis'],
            genesis_b=self.trust['external_secondary_genesis'],
            head_a=self.trust['external_primary_head'],
            head_b=self.trust['external_secondary_head'])

    def body_for(self,i,**change):
        details=evidence.inspect(self.witness_path,
            external_archive_pin=self.archive_pin,**self.trust)
        data=att._claim(('operator-a','operator-b')[i],
            ('fork-witness-operator-a','fork-witness-operator-b')[i],
            self.audit_id,self.challenge[i],1,self.previous[i],
            self.scope,self.archive_pin,
            self.trust['external_primary_genesis'],
            self.trust['external_secondary_genesis'],
            self.trust['external_primary_head'],
            self.trust['external_secondary_head'],details)
        data.update(change)
        return data

    def make_signed(self,i,**change):
        path=Path(self.temp.name)/('synthetic-attest-'+str(i)+'-'+
              str(len(list(Path(self.temp.name).glob('synthetic-attest-*'))))+'.json')
        _sign(self.body_for(i,**change),att.SCHEMA,att.DOMAIN,
              self.observers[i][0],path)
        return path.read_bytes()

    def params(self):
        return dict(
            audit_id=self.audit_id,
            operator_a_id='fork-witness-operator-a',
            operator_b_id='fork-witness-operator-b',
            nonce_a=self.challenge[0],nonce_b=self.challenge[1],
            sequence_a=1,sequence_b=1,
            previous_a=self.previous[0],previous_b=self.previous[1],
            public_a=self.observers[0][1],public_a_pin=self.observers[0][2],
            public_b=self.observers[1][1],public_b_pin=self.observers[1][2],
            envelope_a_pin=self.pins[0],envelope_b_pin=self.pins[1],
            **self.trusted())

    def checked(self,raw_a=None,raw_b=None,**override):
        args=self.params()
        args.update(override)
        return att.verify(self.witness_path,
                          self.raw[0] if raw_a is None else raw_a,
                          self.raw[1] if raw_b is None else raw_b,**args)

    def issue(self,i,**override):
        args=dict(role=('operator-a','operator-b')[i],
             operator_id=('fork-witness-operator-a','fork-witness-operator-b')[i],
             audit_id=self.audit_id,nonce=self.challenge[i],sequence=1,
             previous_pin=self.previous[i],
             signing_private=self.observers[i][0],
             public=self.observers[i][1],public_pin=self.observers[i][2],
             output=self.receipt_paths[i],**self.trusted())
        args.update(override)
        return att.attest(self.witness_path,**args)

    def test_two_independent_signed_claims_and_full_evidence_pass(self):
        r=self.checked()
        self.assertTrue(r['two_distinct_ed25519_operator_keys_verified'])
        self.assertTrue(r['two_independently_pinned_signed_attestations_verified'])
        self.assertTrue(r['archive_reread_and_offline_replay_completed'])
        self.assertEqual(r['conflict_class'],'forked_hash_chains')
        self.assertFalse(r['witness_fence_retired'])

    def test_operator_side_signing_then_verify_reissued_envelopes(self):
        a,b=self.issue(0),self.issue(1)
        r=self.checked(raw_a=self.receipt_paths[0].read_bytes(),
            raw_b=self.receipt_paths[1].read_bytes(),
            envelope_a_pin=a['attestation_envelope_sha256'],
            envelope_b_pin=b['attestation_envelope_sha256'])
        self.assertTrue(r['both_signatures_bind_same_fully_replayed_archive'])
        self.assertFalse(a['external_independent_custody_proved'])
        self.assertFalse(b['offhost_monotonic_attestation_cas_proved'])

    def test_no_clobber_existing_attestation(self):
        self.issue(0)
        before=self.receipt_paths[0].read_bytes()
        with self.assertRaises(FileExistsError):
            self.issue(0)
        self.assertEqual(self.receipt_paths[0].read_bytes(),before)

    def test_signed_after_source_sqlite_deletion_still_valid(self):
        self.registry_path.unlink()
        self.secondary.unlink()
        self.issue(0)
        r=self.checked()
        self.assertTrue(r['archive_reread_and_offline_replay_completed'])

    def test_sign_missing_archive_fails_without_receipt(self):
        self.witness_path.unlink()
        with self.assertRaises((OSError,ValueError)):
            self.issue(0)
        self.assertFalse(self.receipt_paths[0].exists())

    def test_sign_wrong_archive_pin_fails_before_output(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.issue(0,archive_pin='f'*64)
        self.assertFalse(self.receipt_paths[0].exists())

    def test_modified_archive_refused_despite_signed_attestations(self):
        self.witness_path.write_bytes(self.witness_path.read_bytes()+b' ')
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked()

    def test_missing_archive_refused_with_valid_signed_receipts(self):
        self.witness_path.unlink()
        with self.assertRaises((ValueError,OSError)):
            self.checked()

    def test_duplicate_operator_keys_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(public_b=self.observers[0][1],
                         public_b_pin=self.observers[0][2])

    def test_duplicate_operator_identity_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(operator_b_id='fork-witness-operator-a')

    def test_duplicate_challenge_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(nonce_b=self.challenge[0])

    def test_wrong_expected_challenge_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(nonce_a='c'*32)

    def test_invalid_challenge_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(nonce_b='not-128-bit')

    def test_wrong_audit_id_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(audit_id='another-audit')

    def test_wrong_scope_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(scope='unexpected-scope')

    def test_wrong_external_envelope_hash_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(envelope_b_pin='f'*64)

    def test_wrong_external_operator_pem_pin_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(public_a_pin='f'*64)

    def test_wrong_previous_attestation_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(previous_a='f'*64)

    def test_wrong_expected_sequence_rejected(self):
        with self.assertRaises(att.AttestationConflict):
            self.checked(sequence_a=2)

    def test_boolean_sequence_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(sequence_a=True)

    def test_wrong_primary_genesis_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(genesis_a='f'*64)

    def test_wrong_secondary_head_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(head_b='f'*64)

    def test_replaying_other_role_signature_rejected(self):
        with self.assertRaises((ValueError,att.AttestationConflict)):
            self.checked(raw_a=self.raw[1],
                         envelope_a_pin=self.pins[1])

    def test_false_automatic_merge_flag_mandatory(self):
        changed=self.make_signed(0,automatic_ledger_merge_authorized=True)
        with self.assertRaises(att.AttestationConflict):
            self.checked(raw_a=changed,
                envelope_a_pin=hashlib.sha256(changed).hexdigest())

    def test_false_custody_claim_mandatory(self):
        changed=self.make_signed(1,external_independent_custody_proved=True)
        with self.assertRaises(att.AttestationConflict):
            self.checked(raw_b=changed,
                envelope_b_pin=hashlib.sha256(changed).hexdigest())

    def test_signed_wrong_archive_hash_rejected(self):
        changed=self.make_signed(0,archive_sha256='e'*64)
        with self.assertRaises(att.AttestationConflict):
            self.checked(raw_a=changed,
                envelope_a_pin=hashlib.sha256(changed).hexdigest())

    def test_signed_wrong_fork_class_rejected(self):
        changed=self.make_signed(1,conflict_class='strict_prefix_lag')
        with self.assertRaises(att.AttestationConflict):
            self.checked(raw_b=changed,
                envelope_b_pin=hashlib.sha256(changed).hexdigest())

    def test_reports_never_claim_physical_custody_or_fence_release(self):
        report=self.checked()
        for key in ('external_independent_custody_proved',
                    'independently_retained_attestation_pins_proved',
                    'offhost_monotonic_attestation_cas_proved',
                    'signed_operators_honest_proved','global_latest_incident_proved',
                    'automatic_ledger_merge_authorized',
                    'automatic_cas_retry_authorized',
                    'witness_fence_retirement_authorized',
                    'witness_fence_retired','native_switch_game_build_verified'):
            self.assertFalse(report[key],key)

    def cli_args(self):
        args=['verify',str(self.witness_path),
              '--scope',self.scope,'--audit-id',self.audit_id,
              '--archive-pin',self.archive_pin,
              '--primary-genesis-pin',self.trust['external_primary_genesis'],
              '--secondary-genesis-pin',self.trust['external_secondary_genesis'],
              '--primary-head-pin',self.trust['external_primary_head'],
              '--secondary-head-pin',self.trust['external_secondary_head']]
        for i,letter in enumerate(('a','b')):
            path=Path(self.temp.name)/('cli-attestation-'+letter+'.json')
            path.write_bytes(self.raw[i])
            path.chmod(0o600)
            args.extend(['--operator-'+letter+'-id',
                         ('fork-witness-operator-a','fork-witness-operator-b')[i],
                         '--challenge-'+letter,self.challenge[i],
                         '--sequence-'+letter,'1',
                         '--previous-'+letter+'-sha256',self.previous[i],
                         '--public-'+letter,str(self.observers[i][1]),
                         '--public-'+letter+'-pin',self.observers[i][2],
                         '--receipt-'+letter,str(path),
                         '--receipt-'+letter+'-pin',self.pins[i]])
        return args

    def test_cli_verify_redacted_hashes_and_success(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=att.main(self.cli_args())
        r=json.loads(out.getvalue())
        self.assertEqual(status,0,out.getvalue())
        self.assertTrue(r['two_independently_pinned_signed_attestations_verified'])
        self.assertFalse(r['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())

    def test_cli_changed_expected_pin_refused(self):
        argv=self.cli_args()
        argv[argv.index('--receipt-b-pin')+1]='f'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=att.main(argv)
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())[
            'signed_evidence_attestation_conflict'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__=='__main__':
    unittest.main()
