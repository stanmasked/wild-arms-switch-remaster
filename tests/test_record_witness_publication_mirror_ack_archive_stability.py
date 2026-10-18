"""Stage 264V: archive identity/byte stability for full offline Ed25519 replay."""
import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

from tests import test_record_witness_publication_mirror_ack_detached_evidence as base
from tools import audit_record_witness_publication_mirror_ack_detached_evidence as archive


class StableDetachedMirrorAckTests(unittest.TestCase):
    setUpClass=base.DetachedMirrorAckEvidenceTests.__dict__['setUpClass']
    tearDownClass=base.DetachedMirrorAckEvidenceTests.__dict__['tearDownClass']

    def setUp(self):
        base.DetachedMirrorAckEvidenceTests.setUp(self)

    def _interrupt_replay(self,callback):
        original=archive._replay_data
        def after_replay(*args,**kwargs):
            result=original(*args,**kwargs)
            callback()
            return result
        with mock.patch.object(archive,'_replay_data',side_effect=after_replay):
            return self.verify_archive(archive_pin=self._saved_pin)

    def _prepare(self):
        result=self.make_archive()
        self._saved_pin=result['private_evidence_archive_sha256']
        return self.archive_path.read_bytes()

    def test_normal_complete_detached_archive_stable(self):
        self._prepare()
        checked=self.verify_archive(archive_pin=self._saved_pin)
        self.assertEqual(checked['private_evidence_archive_sha256'],self._saved_pin)
        self.assertTrue(checked['every_completed_attestation_signature_reverified_offline'])

    def test_verify_after_all_source_ledgers_deleted(self):
        self._prepare()
        pinned=self.context()
        for path in (self.ack_registry,self.secondary_ack,self.guard_path,self.mirror):
            path.unlink()
        result=archive.inspect(self.archive_path,
            archive_pin=self._saved_pin,**pinned)
        self.assertTrue(result['full_detached_event_chains_replayed_in_memory'])

    def test_replacement_by_new_inode_same_valid_bytes_refused(self):
        raw=self._prepare()
        def swap():
            replacement=Path(self.temp.name)/'prepared-replacement.json'
            replacement.write_bytes(raw)
            replacement.chmod(0o600)
            os.replace(replacement,self.archive_path)
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(swap)

    def test_rewrite_in_place_with_same_bytes_refused(self):
        raw=self._prepare()
        def rewrite():
            self.archive_path.write_bytes(raw)
            st=self.archive_path.stat()
            os.utime(self.archive_path,ns=(st.st_atime_ns,st.st_mtime_ns+3000000000))
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(rewrite)

    def test_archive_modified_during_cryptographic_replay_refused(self):
        self._prepare()
        def tamper():
            self.archive_path.write_bytes(self.archive_path.read_bytes()+b' ')
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(tamper)

    def test_archive_truncated_during_replay_refused(self):
        self._prepare()
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(lambda:self.archive_path.write_bytes(b'{'))

    def test_archive_unlinked_during_replay_refused(self):
        self._prepare()
        with self.assertRaises(OSError):
            self._interrupt_replay(self.archive_path.unlink)

    def test_archive_replaced_with_symlink_during_replay_refused(self):
        self._prepare()
        def symlink_swap():
            alternate=Path(self.temp.name)/'alternate-good-archive.json'
            alternate.write_bytes(self.archive_path.read_bytes())
            alternate.chmod(0o600)
            self.archive_path.unlink()
            self.archive_path.symlink_to(alternate)
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(symlink_swap)

    def test_archive_becomes_hardlinked_during_replay_refused(self):
        self._prepare()
        def add_hardlink():
            os.link(self.archive_path,Path(self.temp.name)/'second-link-to-archive')
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(add_hardlink)

    def test_archive_turned_publicly_readable_during_replay_refused(self):
        self._prepare()
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(lambda:self.archive_path.chmod(0o644))

    def test_archive_replaced_by_directory_during_replay_refused(self):
        self._prepare()
        def replace_directory():
            self.archive_path.unlink()
            self.archive_path.mkdir(mode=0o700)
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self._interrupt_replay(replace_directory)

    def test_no_false_remote_custody_claims_after_stable_read(self):
        self._prepare()
        result=self.verify_archive(archive_pin=self._saved_pin)
        for name in ('independent_external_archive_sha256_retention_proved',
                     'physically_independent_operator_custody_proved',
                     'actual_source_mirror_inspections_replayed_proved',
                     'global_nonce_cas_consensus_proved',
                     'automatic_ledger_merge_authorized',
                     'automatic_pending_recovery_authorized',
                     'automatic_cas_retry_authorized',
                     'witness_fence_retirement_authorized',
                     'witness_fence_retired',
                     'native_switch_game_build_verified'):
            self.assertFalse(result[name],name)

    def test_wrong_external_sha256_still_refused(self):
        self._prepare()
        with self.assertRaises(archive.OfflineMirrorEvidenceConflict):
            self.verify_archive(archive_pin='f'*64)


# Reuse tested Stage U fixture with all original helper names. Never inherit
# Stage U's test methods or shadow ancestral setup methods.
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
    if hasattr(base.DetachedMirrorAckEvidenceTests,name):
        setattr(StableDetachedMirrorAckTests,name,
                getattr(base.DetachedMirrorAckEvidenceTests,name))


if __name__=='__main__':
    unittest.main()
