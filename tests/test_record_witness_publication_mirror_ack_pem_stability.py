"""Stage 264W: detect enrolled Ed25519 PEM replacement during offline replay."""
import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

from tests import test_record_witness_publication_mirror_ack_archive_stability as base
from tools import audit_record_witness_publication_mirror_ack_detached_evidence as archive

REFUSAL=(archive.OfflineMirrorEvidenceConflict,
         archive.private.EvidenceArchiveConflict,
         archive.detached.DetachedHistoryConflict,
         ValueError,OSError)


class DetachedOperatorKeyStabilityTests(unittest.TestCase):
    setUpClass=base.StableDetachedMirrorAckTests.__dict__['setUpClass']
    tearDownClass=base.StableDetachedMirrorAckTests.__dict__['tearDownClass']

    def setUp(self):
        base.StableDetachedMirrorAckTests.setUp(self)

    def prepare(self):
        trusted=self.context()
        created=self.make_archive()
        self.saved_external_trust=trusted
        self.external_archive_pin=created['private_evidence_archive_sha256']
        return created

    def review_after(self,action):
        orig=archive._replay_data
        def replay_then_replace(*args,**kwargs):
            result=orig(*args,**kwargs)
            action()
            return result
        with mock.patch.object(archive,'_replay_data',
                               side_effect=replay_then_replace):
            return archive.inspect(
                self.archive_path,archive_pin=self.external_archive_pin,
                **self.saved_external_trust)

    def test_both_enrolled_keys_remain_stable(self):
        self.prepare()
        result=archive.inspect(
            self.archive_path,archive_pin=self.external_archive_pin,
            **self.saved_external_trust)
        self.assertTrue(result['every_completed_attestation_signature_reverified_offline'])

    def test_registered_keys_checked_without_source_databases(self):
        self.prepare()
        for path in (self.ack_registry,self.secondary_ack,self.guard_path,self.mirror):
            path.unlink()
        result=archive.inspect(
            self.archive_path,archive_pin=self.external_archive_pin,
            **self.saved_external_trust)
        self.assertTrue(result['full_detached_event_chains_replayed_in_memory'])

    def test_swap_operator_a_public_pem_with_same_bytes_rejected(self):
        self.prepare()
        public=Path(self.observers[0][1])
        def swap():
            replacement=Path(self.temp.name)/'replacement-operator-a.pem'
            replacement.write_bytes(public.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement,public)
        with self.assertRaises(REFUSAL):
            self.review_after(swap)

    def test_swap_uncompleted_operator_b_public_pem_with_same_bytes_rejected(self):
        # Only operator A has a completed signature in this fixture.
        # The enrolled but as yet unsigned operator B must still be stable.
        self.prepare()
        public=Path(self.observers[1][1])
        def swap():
            replacement=Path(self.temp.name)/'replacement-operator-b.pem'
            replacement.write_bytes(public.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement,public)
        with self.assertRaises(REFUSAL):
            self.review_after(swap)

    def test_rewrite_operator_a_public_pem_in_place_rejected(self):
        self.prepare()
        public=Path(self.observers[0][1])
        def rewrite():
            raw=public.read_bytes()
            public.write_bytes(raw)
            st=public.stat()
            os.utime(public,ns=(st.st_atime_ns,st.st_mtime_ns+3_000_000_000))
        with self.assertRaises(REFUSAL):
            self.review_after(rewrite)

    def test_operator_b_public_pem_permissions_weakened_rejected(self):
        self.prepare()
        public=Path(self.observers[1][1])
        with self.assertRaises(REFUSAL):
            self.review_after(lambda:public.chmod(0o644))

    def test_operator_a_public_pem_hardlink_introduced_rejected(self):
        self.prepare()
        public=Path(self.observers[0][1])
        def link():
            os.link(public,Path(self.temp.name)/'duplicate-signing-pem-link')
        with self.assertRaises(REFUSAL):
            self.review_after(link)

    def test_operator_b_public_pem_symlink_swap_rejected(self):
        self.prepare()
        public=Path(self.observers[1][1])
        def symlink():
            alternate=Path(self.temp.name)/'alternate-public-key.pem'
            alternate.write_bytes(public.read_bytes())
            alternate.chmod(0o600)
            public.unlink()
            public.symlink_to(alternate)
        with self.assertRaises(REFUSAL):
            self.review_after(symlink)

    def test_operator_a_public_pem_deleted_during_replay_rejected(self):
        self.prepare()
        with self.assertRaises(REFUSAL):
            self.review_after(Path(self.observers[0][1]).unlink)

    def test_operator_b_public_pem_truncated_during_replay_rejected(self):
        self.prepare()
        public=Path(self.observers[1][1])
        with self.assertRaises(REFUSAL):
            self.review_after(lambda:public.write_bytes(b''))

    def test_different_other_registered_key_for_a_rejected_at_start(self):
        self.prepare()
        trusted=dict(self.saved_external_trust,
            operator_a_public=self.observers[1][1])
        with self.assertRaises(REFUSAL):
            archive.inspect(self.archive_path,
                archive_pin=self.external_archive_pin,**trusted)

    def test_different_other_registered_key_for_b_rejected_at_start(self):
        self.prepare()
        trusted=dict(self.saved_external_trust,
            operator_b_public=self.observers[0][1])
        with self.assertRaises(REFUSAL):
            archive.inspect(self.archive_path,
                archive_pin=self.external_archive_pin,**trusted)

    def test_public_key_replaced_by_directory_mid_replay_rejected(self):
        self.prepare()
        public=Path(self.observers[1][1])
        def directory():
            public.unlink()
            public.mkdir(mode=0o700)
        with self.assertRaises(REFUSAL):
            self.review_after(directory)

    def test_no_offhost_key_custody_claims_after_stability_check(self):
        self.prepare()
        checked=archive.inspect(
            self.archive_path,archive_pin=self.external_archive_pin,
            **self.saved_external_trust)
        for field in ('physically_independent_operator_custody_proved',
            'independent_external_archive_sha256_retention_proved',
            'actual_source_mirror_inspections_replayed_proved',
            'global_nonce_cas_consensus_proved',
            'automatic_ledger_merge_authorized',
            'automatic_pending_recovery_authorized',
            'witness_fence_retirement_authorized',
            'witness_fence_retired',
            'native_switch_game_build_verified'):
            self.assertFalse(checked[field],field)


# Reuse fixtures but NEVER inherit test methods.
for name in (
    'sign','compute_pin','fetch','_advanced_keeper','certificate','body',
    'endorse','bundle','args','check','create','inspect','arguments',
    'copy_args','clone','signed_body','sign_receipt','operator_args',
    'make_fields','reserve','sign_one','kwargs','crosscheck','write',
    'create_witness','inspect_witness','trusted','body_for','make_signed',
    'checked','issue','guarded','snapshot','advance','seal_mirror',
    'params','check_mirror','one_complete','build_manifest',
    'expected_ack_body','signed_ack','verify','ack_arguments',
    'sign_guarded_ack','ack_snapshot',
    'issue_ack','mirror_acks','trusted_acks','audit_acks','prepare_first_ack',
    'write_manifest','context','make_archive','verify_archive','alter_archive'
):
    if hasattr(base.StableDetachedMirrorAckTests,name):
        setattr(DetachedOperatorKeyStabilityTests,name,
                getattr(base.StableDetachedMirrorAckTests,name))


if __name__=='__main__':
    unittest.main()
