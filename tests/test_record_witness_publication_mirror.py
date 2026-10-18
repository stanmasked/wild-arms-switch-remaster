"""Stage 263R: comparison of two pinned local publication journals."""
import shutil
import sqlite3
import unittest
from tests import test_record_witness_publication_intake as prior
from tools import audit_record_witness_publication_mirror as mirror
from tools import audit_record_witness_publication_intake as intake


class PublicationMirrorTests(prior.SignedPublicationIntakeTests):
    # Inherit full private witness fixture; only test_ methods added below
    # are mirror-specific (the inherited tests remain independent).
    def duplicate(self):
        second=self.v/'independent-copy.sqlite'
        shutil.copyfile(self.intake_path,second)
        second.chmod(0o600)
        return second

    def test_two_genesis_mirrors_match_without_unlock(self):
        self.setup_intake(0)
        other=self.duplicate()
        result=mirror.compare(self.intake_path,0,intake.GENESIS,
                              other,0,intake.GENESIS)
        self.assertTrue(result['identical_full_event_histories'])
        self.assertFalse(result['witness_fence_retired'])
        self.assertFalse(result['separate_physical_storage_proved'])

    def test_complete_nonempty_replica_matches(self):
        self.setup_intake(0)
        self.full_round(0)
        other=self.duplicate()
        result=mirror.compare(self.intake_path,3,self.i_head,
                              other,3,self.i_head)
        self.assertEqual(result['event_count'],3)

    def test_stale_prefix_refused(self):
        self.setup_intake(0)
        other=self.duplicate()
        self.submit(0,'escrow-a')
        with self.assertRaises(mirror.MirrorConflict):
            mirror.compare(self.intake_path,1,self.i_head,
                           other,0,intake.GENESIS)

    def test_tampered_second_chain_refused(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        other=self.duplicate()
        with sqlite3.connect(other) as db:
            db.execute("UPDATE published_escrow_receipts SET round_nonce=?",
                       ('f'*32,))
        with self.assertRaises(intake.PublicationConflict):
            mirror.compare(self.intake_path,1,self.i_head,
                           other,1,self.i_head)

    def test_wrong_external_pin_refused(self):
        self.setup_intake(0)
        other=self.duplicate()
        with self.assertRaises(intake.PublicationConflict):
            mirror.compare(self.intake_path,0,intake.GENESIS,
                           other,0,'f'*64)

    def test_same_path_cannot_masquerade_as_two_archives(self):
        self.setup_intake(0)
        with self.assertRaises(mirror.MirrorConflict):
            mirror.compare(self.intake_path,0,intake.GENESIS,
                           self.intake_path,0,intake.GENESIS)

    def test_conflict_frozen_mirror_is_preserved(self):
        self.setup_intake(0)
        self.submit(0,'escrow-a')
        conflicting=self.conflicting_receipt(0,'escrow-a',nonce='a'*32)
        self.submit(0,'escrow-a',conflicting)
        other=self.duplicate()
        result=mirror.compare(self.intake_path,2,self.i_head,
                              other,2,self.i_head)
        self.assertTrue(result['intake_frozen_by_conflict'])
        self.assertFalse(result['witness_fence_retirement_authorized'])

    def test_two_different_valid_branches_refused(self):
        self.setup_intake(0)
        other=self.duplicate()
        self.submit(0,'escrow-a')
        variant=self.conflicting_receipt(0,'escrow-a',nonce='a'*32)
        original=self.intake_path
        self.intake_path=other
        try:
            branch=self.submit(0,'escrow-a',variant)
        finally:
            self.intake_path=original
        with self.assertRaises(mirror.MirrorConflict):
            mirror.compare(original,1,self.i_head,
                           other,1,branch['intake_head_sha256'])


if __name__=='__main__':
    unittest.main()
