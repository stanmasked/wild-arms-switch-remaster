"""Stage 263U: independently pinned comparison of two valid signed histories."""
import contextlib
import hashlib
import io
import json
import unittest

from tests import test_record_witness_publication_mirror_history as fixture
from tools import audit_record_witness_publication_archive_compare as compare
from tools import audit_record_witness_publication_mirror_history as history
from tools import audit_record_witness_publication_mirror_witness as witness
from tools import audit_record_witness_publication_intake as intake

TAG = 'private-wild-arms-publication-mirrors'


class TwoSignedArchiveTests(unittest.TestCase):
    setUp=fixture.SignedMirrorHistoryTests.setUp
    path=fixture.SignedMirrorHistoryTests.path
    request=fixture.SignedMirrorHistoryTests.request
    stop=fixture.SignedMirrorHistoryTests.stop
    make_cgroup=fixture.SignedMirrorHistoryTests.make_cgroup
    write_controls=fixture.SignedMirrorHistoryTests.write_controls
    snapshot=fixture.SignedMirrorHistoryTests.snapshot
    signed_stop_for=fixture.SignedMirrorHistoryTests.signed_stop_for
    new_offer=fixture.SignedMirrorHistoryTests.new_offer
    make_offer_and_deposit=fixture.SignedMirrorHistoryTests.make_offer_and_deposit
    init_capture=fixture.SignedMirrorHistoryTests.init_capture
    build=fixture.SignedMirrorHistoryTests.build
    prepare=fixture.SignedMirrorHistoryTests.prepare
    init_journal=fixture.SignedMirrorHistoryTests.init_journal
    enroll=fixture.SignedMirrorHistoryTests.enroll
    second_bundle=fixture.SignedMirrorHistoryTests.second_bundle
    sign_heads=fixture.SignedMirrorHistoryTests.sign_heads
    fresh=fixture.SignedMirrorHistoryTests.fresh
    first_candidate=fixture.SignedMirrorHistoryTests.first_candidate
    accept=fixture.SignedMirrorHistoryTests.accept
    signed_round=fixture.SignedMirrorHistoryTests.signed_round
    stage=fixture.SignedMirrorHistoryTests.stage
    setup_intake=fixture.SignedMirrorHistoryTests.setup_intake
    submit=fixture.SignedMirrorHistoryTests.submit
    full_round=fixture.SignedMirrorHistoryTests.full_round
    conflicting_receipt=fixture.SignedMirrorHistoryTests.conflicting_receipt
    duplicate=fixture.SignedMirrorHistoryTests.duplicate
    sign_epoch=fixture.SignedMirrorHistoryTests.sign_epoch
    build_history=fixture.SignedMirrorHistoryTests.build_history
    check=fixture.SignedMirrorHistoryTests.check

    @classmethod
    def setUpClass(cls):
        fixture.SignedMirrorHistoryTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(fixture.SignedMirrorHistoryTests,name))

    @classmethod
    def tearDownClass(cls):
        fixture.SignedMirrorHistoryTests.tearDownClass()

    def compare(self, *, second_raw=None, second_pin=None,
                second_tip=None, first_raw=None, first_pin=None,
                first_tip=None, second_b=None):
        return compare.compare(
            self.intake_path,self.i_count,self.i_head,
            self.mirror_b if second_b is None else second_b,
            self.i_count,self.i_head,
            self.archive if first_raw is None else first_raw,
            self.archive_pin if first_pin is None else first_pin,
            self.latest if first_tip is None else first_tip,
            self.archive if second_raw is None else second_raw,
            self.archive_pin if second_pin is None else second_pin,
            self.latest if second_tip is None else second_tip,
            self.admins[0][2],self.admins[0][3],
            self.admins[1][2],self.admins[1][3],scope=TAG)

    def alternative(self):
        # Two valid histories over the very same publication journals:
        # different independently signed epoch-0 claim changes its digest,
        # and all later claims must reflect the changed previous digest.
        alternative=[]
        prior=witness.WITNESS_GENESIS
        for epoch in range(self.i_count+1):
            head=(intake.GENESIS if epoch==0 else
                  json.loads(self.claims[epoch][witness.ROLES[0]])[
                      'body']['mirror_head_sha256'])
            frozen=(epoch>=4)
            row=self.sign_epoch(epoch,head,frozen,prior,
                                nonce=format(100+epoch,'032x'))
            alternative.append(row)
            prior=witness.witness_digest(row[witness.ROLES[0]],
                                        row[witness.ROLES[1]])
        raw=history.pack(alternative)
        return raw,hashlib.sha256(raw).hexdigest(),prior

    def test_genesis_two_independently_pinned_archives_match(self):
        self.build_history(0)
        result=self.compare()
        self.assertTrue(result['both_signed_archives_individually_verified'])
        self.assertTrue(result['all_submitted_signed_epochs_identical'])
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['separate_archive_storage_proved'])

    def test_complete_nonempty_matching_archives(self):
        self.build_history(2)
        result=self.compare()
        self.assertEqual(result['complete_signed_rounds_compared'],3)

    def test_conflict_frozen_valid_archives_may_match_without_release(self):
        self.build_history(4)
        result=self.compare()
        self.assertEqual(result['complete_signed_rounds_compared'],5)
        self.assertFalse(result['witness_fence_retired'])

    def test_two_valid_but_distinct_signed_histories_refused(self):
        self.build_history(1)
        raw,pin,tip=self.alternative()
        # Both signed histories validate independently, but they
        # contain conflicting signed epoch commitments.
        self.check(raw=raw,pin=pin,latest=tip)
        with self.assertRaises(compare.ArchiveConflict):
            self.compare(second_raw=raw,second_pin=pin,second_tip=tip)

    def test_conflicting_valid_genesis_signatures_refused(self):
        self.build_history(0)
        raw,pin,tip=self.alternative()
        with self.assertRaises(compare.ArchiveConflict):
            self.compare(second_raw=raw,second_pin=pin,second_tip=tip)

    def test_unpinned_second_archive_file_rejected(self):
        self.build_history(0)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.compare(second_pin='f'*64)

    def test_stale_second_latest_witness_pin_refused(self):
        self.build_history(1)
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.compare(second_tip=witness.WITNESS_GENESIS)

    def test_old_partial_history_refused_even_with_own_sha(self):
        self.build_history(2)
        partial=history.pack(self.claims[:2])
        with self.assertRaises(history.SnapshotHistoryConflict):
            self.compare(second_raw=partial,
                         second_pin=hashlib.sha256(partial).hexdigest())

    def test_same_underlying_mirror_path_refused(self):
        self.build_history(0)
        with self.assertRaises(history.MirrorConflict):
            self.compare(second_b=self.intake_path)

    def test_corrupt_signature_in_second_archive_not_saved_by_repin(self):
        self.build_history(0)
        corrupted=[dict(self.claims[0])]
        corrupted[0][witness.ROLES[1]]=corrupted[0][witness.ROLES[0]]
        raw=history.pack(corrupted)
        with self.assertRaises(ValueError):
            self.compare(second_raw=raw,
                         second_pin=hashlib.sha256(raw).hexdigest())

    def test_two_archives_with_old_matching_pins_cannot_prove_freshness(self):
        self.build_history(0)
        result=self.compare()
        self.assertFalse(result['synchronized_old_archives_and_old_pins_excluded'])
        self.assertFalse(result['externally_enrolled_tips_are_globally_latest_proved'])

    def test_redacted_cli_success_and_no_release(self):
        self.build_history(0)
        second=self.path('second-signed-private-archive-')
        second.write_bytes(self.archive)
        second.chmod(0o600)
        args=[
            str(self.intake_path),str(self.mirror_b),
            str(self.archive_file),self.archive_pin,
            str(second),self.archive_pin,
            '--a-count','0','--a-head',intake.GENESIS,
            '--b-count','0','--b-head',intake.GENESIS,
            '--admin-a-public',str(self.admins[0][2]),
            '--admin-a-public-pin',self.admins[0][3],
            '--admin-b-public',str(self.admins[1][2]),
            '--admin-b-public-pin',self.admins[1][3],
            '--scope',TAG,
            '--first-latest-witness-sha256',self.latest,
            '--second-latest-witness-sha256',self.latest,
        ]
        with contextlib.redirect_stdout(output := io.StringIO()):
            code=compare.main(args)
        self.assertEqual(code,0,output.getvalue())
        self.assertFalse(json.loads(output.getvalue())['witness_fence_retired'])
        self.assertNotIn('signature_hex',output.getvalue())
        self.assertNotIn('witness_nonce',output.getvalue())


if __name__=='__main__':
    unittest.main()
