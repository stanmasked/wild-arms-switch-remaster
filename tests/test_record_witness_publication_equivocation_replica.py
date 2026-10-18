"""Stage 264G synthetic tests: dual private evidence copies and readback."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from tests import test_record_witness_publication_equivocation_archive as fixture
from tools import audit_record_witness_publication_equivocation_replica as copies
from tools import audit_record_witness_publication_equivocation_archive as archive


class EvidenceReplicaTests(unittest.TestCase):
    setUpClass=fixture.EvidenceArchiveTests.__dict__['setUpClass']
    tearDownClass=fixture.EvidenceArchiveTests.__dict__['tearDownClass']
    sign=fixture.EvidenceArchiveTests.sign
    compute_pin=fixture.EvidenceArchiveTests.compute_pin
    fetch=fixture.EvidenceArchiveTests.fetch
    _advanced_keeper=fixture.EvidenceArchiveTests._advanced_keeper
    certificate=fixture.EvidenceArchiveTests.certificate
    body=fixture.EvidenceArchiveTests.body
    endorse=fixture.EvidenceArchiveTests.endorse
    bundle=fixture.EvidenceArchiveTests.bundle
    args=fixture.EvidenceArchiveTests.args
    check=fixture.EvidenceArchiveTests.check
    create=fixture.EvidenceArchiveTests.create
    inspect=fixture.EvidenceArchiveTests.inspect

    def setUp(self):
        fixture.EvidenceArchiveTests.setUp(self)
        self.first=self.create()
        self.primary_pin=self.first['archive_sha256']
        self.second_dir=Path(self.temp.name)/'separate-admin-folder'
        self.second_dir.mkdir(mode=0o700)
        self.second_dir.chmod(0o700)
        self.secondary=self.second_dir/'signed-evidence-copy.json'

    def arguments(self):
        return dict(primary_pin=self.primary_pin,
                    secondary_pin=self.primary_pin,
                    evidence_pin=self.evidence_sha,
                    operator_a_public=self.observers[0][1],
                    operator_b_public=self.observers[1][1],
                    external_operator_a_pin=self.observers[0][2],
                    external_operator_b_pin=self.observers[1][2])

    def copy_args(self):
        args=self.arguments()
        args.pop('secondary_pin')
        return args

    def clone(self):
        return copies.replicate(self.archive,self.secondary,**self.copy_args())

    def verify(self,**change):
        args=self.arguments()
        args.update(change)
        return copies.verify(self.archive,self.secondary,**args)

    def test_exclusive_copy_reaudits_two_signer_archives(self):
        result=self.clone()
        self.assertTrue(result['local_secondary_no_replace_creation_verified'])
        self.assertTrue(result['both_archives_revalidated_twice_with_ed25519'])
        self.assertEqual(result['local_archive_copy_count_observed'],2)
        self.assertEqual(result['canonical_evidence_sha256'],self.evidence_sha)
        self.assertNotEqual(self.archive.stat().st_ino,
                            self.secondary.stat().st_ino)
        self.assertFalse(result['independent_operator_or_offhost_storage_proved'])

    def test_repeat_read_only_audit_matches_pinned_both_files(self):
        self.clone()
        v=self.verify()
        self.assertTrue(v['both_archive_sha256_pins_matched'])
        self.assertTrue(v['both_archives_exact_bytes_equal_in_two_rounds'])
        self.assertFalse(v.get('local_secondary_no_replace_creation_verified',False))

    def test_replication_never_overwrites_existing_copy(self):
        self.clone()
        previous=self.secondary.read_bytes()
        with self.assertRaises(copies.DualCopyConflict):
            self.clone()
        self.assertEqual(previous,self.secondary.read_bytes())

    def test_replicate_refuses_secondary_pin_it_did_not_read(self):
        self.clone()
        with self.assertRaises(copies.DualCopyConflict):
            copies.replicate(self.archive,self.secondary,**self.copy_args())

    def test_missing_primary_copy_fail_closed(self):
        self.archive.unlink()
        with self.assertRaises((ValueError,OSError,copies.DualCopyConflict)):
            self.clone()
        self.assertFalse(self.secondary.exists())

    def test_missing_secondary_copy_fail_closed(self):
        with self.assertRaises((ValueError,OSError,copies.DualCopyConflict)):
            self.verify()

    def test_deleted_secondary_with_original_pin_detected(self):
        self.clone()
        self.secondary.unlink()
        with self.assertRaises((ValueError,OSError,copies.DualCopyConflict)):
            self.verify()

    def test_deleted_primary_with_pins_detected(self):
        self.clone()
        self.archive.unlink()
        with self.assertRaises((ValueError,OSError,copies.DualCopyConflict)):
            self.verify()

    def test_changed_secondary_bytes_with_old_pin_detected(self):
        self.clone()
        self.secondary.write_bytes(self.secondary.read_bytes()[:-1])
        with self.assertRaises(copies.DualCopyConflict):
            self.verify()

    def test_changed_primary_bytes_with_old_pin_detected(self):
        self.clone()
        self.archive.write_bytes(self.archive.read_bytes()+b' ')
        with self.assertRaises(copies.DualCopyConflict):
            self.verify()

    def test_wrong_primary_external_pin_rejected(self):
        self.clone()
        with self.assertRaises(copies.DualCopyConflict):
            self.verify(primary_pin='f'*64)

    def test_wrong_secondary_external_pin_rejected(self):
        self.clone()
        with self.assertRaises(copies.DualCopyConflict):
            self.verify(secondary_pin='f'*64)

    def test_wrong_canonical_evidence_hash_rejected(self):
        self.clone()
        with self.assertRaises((ValueError,copies.DualCopyConflict)):
            self.verify(evidence_pin='f'*64)

    def test_wrong_operator_key_pin_rejected(self):
        self.clone()
        with self.assertRaises((ValueError,copies.DualCopyConflict)):
            self.verify(external_operator_a_pin='f'*64)

    def test_same_directory_two_files_refused(self):
        same=self.archive.parent/'secondary-in-same-directory.json'
        shutil.copyfile(self.archive,same)
        same.chmod(0o600)
        with self.assertRaises(copies.DualCopyConflict):
            copies.verify(self.archive,same,**self.arguments())

    def test_replication_into_same_directory_refused_without_creation(self):
        same=self.archive.parent/'would-replicate.json'
        with self.assertRaises(copies.DualCopyConflict):
            copies.replicate(self.archive,same,**self.copy_args())
        self.assertFalse(same.exists())

    def test_same_underlying_file_refused(self):
        with self.assertRaises(copies.DualCopyConflict):
            copies.verify(self.archive,self.archive,**self.arguments())

    def test_hardlinked_archive_replica_refused(self):
        os.link(self.archive,self.secondary)
        with self.assertRaises(copies.DualCopyConflict):
            self.verify()

    def test_symlink_to_first_archive_refused(self):
        self.secondary.symlink_to(self.archive)
        with self.assertRaises(archive.EvidenceArchiveConflict):
            self.verify()

    def test_symlink_to_secondary_directory_refused(self):
        alias=Path(self.temp.name)/'alias-folder'
        alias.symlink_to(self.second_dir,target_is_directory=True)
        self.clone()
        with self.assertRaises(archive.EvidenceArchiveConflict):
            copies.verify(self.archive,alias/self.secondary.name,
                          **self.arguments())

    def test_world_accessible_secondary_directory_refused(self):
        self.clone()
        self.second_dir.chmod(0o755)
        self.addCleanup(self.second_dir.chmod,0o700)
        with self.assertRaises(archive.EvidenceArchiveConflict):
            self.verify()

    def test_world_readable_secondary_file_refused(self):
        self.clone()
        self.secondary.chmod(0o644)
        with self.assertRaises(copies.DualCopyConflict):
            self.verify()

    def test_changed_file_inode_between_audit_rounds_refused(self):
        self.clone()
        original=copies._separate
        calls=[0]
        def injected(a,b):
            calls[0]+=1
            result=original(a,b)
            if calls[0]==2:
                replacement=self.second_dir/'replacement.json'
                shutil.copyfile(self.secondary,replacement)
                replacement.chmod(0o600)
                os.replace(replacement,self.secondary)
            return result
        with mock.patch.object(copies,'_separate',side_effect=injected):
            with self.assertRaises(copies.DualCopyConflict):
                self.verify()

    def test_changed_readback_bytes_during_audit_refused(self):
        self.clone()
        actual=copies._read_digest
        calls=[0]
        def changed(path,pin):
            calls[0]+=1
            if calls[0]==3:
                # Simulated untrustworthy readback of the same pathname
                return b'changed-after-first-read'
            return actual(path,pin)
        with mock.patch.object(copies,'_read_digest',side_effect=changed):
            with self.assertRaises(copies.DualCopyConflict):
                self.verify()

    def test_unsafe_replication_does_not_create_file(self):
        self.second_dir.chmod(0o755)
        self.addCleanup(self.second_dir.chmod,0o700)
        with self.assertRaises(archive.EvidenceArchiveConflict):
            self.clone()
        self.assertFalse(self.secondary.exists())

    def test_output_never_claims_durable_independent_custody(self):
        r=self.clone()
        for field in ('independent_operator_or_offhost_storage_proved',
                      'independent_external_pin_retention_proved',
                      'tamper_or_deletion_prevention_proved',
                      'physical_durability_proved',
                      'globally_latest_archive_proved',
                      'either_branch_keeper_commit_proved',
                      'automatic_cas_retry_authorized',
                      'witness_fence_retired',
                      'native_switch_game_build_verified'):
            self.assertFalse(r[field],field)

    def test_cli_read_only_requires_secondary_pin(self):
        self.clone()
        argv=['verify',str(self.archive),str(self.secondary),
            '--primary-pin',self.primary_pin,'--evidence-pin',self.evidence_sha,
            '--operator-a-public',str(self.observers[0][1]),
            '--operator-b-public',str(self.observers[1][1]),
            '--operator-a-pin',self.observers[0][2],
            '--operator-b-pin',self.observers[1][2]]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=copies.main(argv)
        obj=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertTrue(obj['replica_integrity_conflict'])
        self.assertFalse(obj['witness_fence_retired'])

    def test_cli_verify_redacted_and_no_fence_release(self):
        self.clone()
        argv=['verify',str(self.archive),str(self.secondary),
            '--primary-pin',self.primary_pin,'--secondary-pin',self.primary_pin,
            '--evidence-pin',self.evidence_sha,
            '--operator-a-public',str(self.observers[0][1]),
            '--operator-b-public',str(self.observers[1][1]),
            '--operator-a-pin',self.observers[0][2],
            '--operator-b-pin',self.observers[1][2]]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=copies.main(argv)
        obj=json.loads(out.getvalue())
        self.assertEqual(status,0,out.getvalue())
        self.assertTrue(obj['both_archives_revalidated_twice_with_ed25519'])
        self.assertFalse(obj['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())

    def test_cli_replicate_with_secondary_pin_refused(self):
        argv=['replicate',str(self.archive),str(self.secondary),
            '--primary-pin',self.primary_pin,'--secondary-pin',self.primary_pin,
            '--evidence-pin',self.evidence_sha,
            '--operator-a-public',str(self.observers[0][1]),
            '--operator-b-public',str(self.observers[1][1]),
            '--operator-a-pin',self.observers[0][2],
            '--operator-b-pin',self.observers[1][2]]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=copies.main(argv)
        obj=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertTrue(obj['replica_integrity_conflict'])
        self.assertFalse(self.secondary.exists())


if __name__=='__main__':
    unittest.main()
