"""Stage450: synthetic PCSX-Redux GPUDUMP v1r1 VSync chronology regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_private_pcsx_native_vsync_chronology import (
    audit_private_native_vsync,inspect_native_vsync_chronology)
from import_private_pcsx_native_gpudump import (
    GP0,GP1,VSYNC,TRACE_BEGIN,read_native_gpu_dump)
from test_import_private_pcsx_native_gpudump import base_records,dump_bytes


def checked(records,**kwargs):
    return inspect_native_vsync_chronology(
        read_native_gpu_dump(dump_bytes(records)),**kwargs)


class Stage450VSyncChronologyTests(unittest.TestCase):
    def test_one_normal_recorded_frame_ends_on_first_vsync(self):
        report=checked(base_records())
        self.assertEqual(report["chronology_status"],
                         "COMPLETE_VSYNC_BOUNDARIES_IN_TYPED_DUMP")
        self.assertEqual(report["completed_post_trace_vsync_count"],1)
        self.assertEqual(report["first_vsync_cycle_stamp"],1234)
        self.assertTrue(report["native_dump_ends_on_complete_vsync_record"])
        self.assertTrue(report["native_typed_boundaries_chronologically_coherent"])
        self.assertIsNone(report["minimum_vsync_cycle_delta"])

    def test_multiple_completed_frames_have_positive_64bit_deltas(self):
        rec=base_records()
        rec.extend([(GP0,[0]),(VSYNC,[1254,0]),(VSYNC,[1284,0])])
        report=checked(rec)
        self.assertEqual(report["completed_post_trace_vsync_count"],3)
        self.assertEqual(report["first_vsync_cycle_delta_samples"],[20,30])
        self.assertEqual(report["minimum_vsync_cycle_delta"],20)
        self.assertEqual(report["maximum_vsync_cycle_delta"],30)
        self.assertTrue(report["native_dump_ends_on_complete_vsync_record"])

    def test_64bit_counter_high_word_is_used_for_monotonicity(self):
        rec=base_records()
        rec[-1]=(VSYNC,[0xfffffff0,9])
        rec.append((VSYNC,[0x00000010,10]))
        report=checked(rec)
        self.assertEqual(report["first_vsync_cycle_delta_samples"],[32])
        self.assertTrue(report["all_completed_vsync_stamps_strictly_increasing"])

    def test_equal_vsync_timestamps_are_not_considered_new_time(self):
        rec=base_records()
        rec.append((VSYNC,[1234,0]))
        report=checked(rec)
        self.assertEqual(report["chronology_status"],
                         "NONMONOTONIC_VSYNC_CYCLE_STAMPS")
        self.assertEqual(report["non_increasing_vsync_interval_count"],1)
        self.assertFalse(report["native_dump_ends_on_complete_vsync_record"])

    def test_decreasing_vsync_timestamps_are_rejected_as_chronology_proof(self):
        rec=base_records()
        rec.append((VSYNC,[1222,0]))
        report=checked(rec)
        self.assertEqual(report["non_increasing_vsync_interval_count"],1)
        self.assertFalse(report["native_typed_boundaries_chronologically_coherent"])

    def test_duplicate_trace_begin_flags_ambiguous_capture(self):
        rec=base_records()
        rec.insert(-1,(TRACE_BEGIN,[]))
        report=checked(rec)
        self.assertEqual(report["trace_begin_marker_count"],2)
        self.assertEqual(report["chronology_status"],
                         "TRACE_BEGIN_MISSING_OR_DUPLICATE")
        self.assertFalse(report["native_dump_ends_on_complete_vsync_record"])

    def test_missing_trace_begin_not_interpreted_as_valid_frame(self):
        rec=[item for item in base_records() if item[0]!=TRACE_BEGIN]
        report=checked(rec)
        self.assertEqual(report["trace_begin_marker_count"],0)
        self.assertEqual(report["completed_post_trace_vsync_count"],0)
        self.assertEqual(report["chronology_status"],
                         "TRACE_BEGIN_MISSING_OR_DUPLICATE")

    def test_vsync_before_trace_begin_is_not_a_first_live_frame(self):
        rec=base_records()
        start=next(i for i,(k,_) in enumerate(rec) if k==TRACE_BEGIN)
        rec.insert(start,(VSYNC,[200,0]))
        report=checked(rec)
        self.assertEqual(report["prelude_vsync_record_count"],1)
        self.assertEqual(report["completed_post_trace_vsync_count"],1)
        self.assertEqual(report["chronology_status"],
                         "PRELUDE_VSYNC_BEFORE_TRACE_BEGIN")

    def test_no_post_trace_vsync_is_not_a_completed_native_frame(self):
        rec=base_records()[:-1]
        report=checked(rec)
        self.assertEqual(report["chronology_status"],
                         "NO_COMPLETED_POST_TRACE_VSYNC")
        self.assertFalse(report["native_dump_ends_on_complete_vsync_record"])

    def test_live_gp0_after_last_vsync_is_trailing_partial_frame(self):
        rec=base_records()
        rec.append((GP0,[0]))
        report=checked(rec)
        self.assertEqual(report["event_records_after_last_vsync"],1)
        self.assertEqual(report["live_gpu_transport_records_after_last_vsync"],1)
        self.assertEqual(report["chronology_status"],
                         "TRAILING_PARTIAL_NATIVE_FRAME")
        self.assertTrue(report["native_typed_boundaries_chronologically_coherent"])
        self.assertFalse(report["native_dump_ends_on_complete_vsync_record"])

    def test_vsync_as_final_record_proves_only_structural_boundary(self):
        report=checked(base_records())
        self.assertTrue(report["interpretation"][
            "monotonic_vsync_does_not_authenticate_emulator_executable"])
        self.assertTrue(report["interpretation"][
            "whole_dump_record_boundaries_not_proof_of_gp0_packet_completeness"])

    def test_expected_frame_count_exact_match_and_mismatch(self):
        normal=checked(base_records(),expected_completed_frames=1)
        self.assertTrue(normal["expected_completed_frame_count_matches"])
        bad=checked(base_records(),expected_completed_frames=2)
        self.assertFalse(bad["native_typed_boundaries_chronologically_coherent"])
        self.assertEqual(bad["chronology_status"],
                         "UNEXPECTED_COMPLETED_FRAME_COUNT")

    def test_vsync_sample_cap_retains_full_count(self):
        rec=base_records()+[(VSYNC,[2000,0]),(VSYNC,[3000,0]),
                            (VSYNC,[4000,0])]
        report=checked(rec,max_interval_samples=1)
        self.assertEqual(report["completed_post_trace_vsync_count"],4)
        self.assertEqual(report["first_vsync_cycle_delta_samples"],[766])
        self.assertTrue(report["vsync_delta_samples_truncated"])

    def test_preflight_reports_matching_independent_chronology(self):
        from preflight_private_pcsx_native_gpudump import summarize_private_native_gpudump
        report=summarize_private_native_gpudump(dump_bytes())
        timing=report["native_vsync_chronology"]
        self.assertEqual(timing["completed_post_trace_vsync_count"],1)
        self.assertTrue(timing["native_dump_ends_on_complete_vsync_record"])

    def test_preflight_keeps_incomplete_frames_diagnostic_not_silent(self):
        from preflight_private_pcsx_native_gpudump import summarize_private_native_gpudump
        blob=dump_bytes(base_records()+[(GP0,[0])])
        report=summarize_private_native_gpudump(blob)
        self.assertTrue(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertFalse(report["native_vsync_chronology"][
            "native_dump_ends_on_complete_vsync_record"])

    def test_bad_argument_types_refused(self):
        records=read_native_gpu_dump(dump_bytes())
        for kwargs in (
            {"max_interval_samples":True},{"max_interval_samples":0},
            {"max_interval_samples":65},
            {"expected_completed_frames":True},
            {"expected_completed_frames":0},
            {"expected_completed_frames":20001},
        ):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                inspect_native_vsync_chronology(records,**kwargs)
        with self.assertRaises(ValueError):
            inspect_native_vsync_chronology([("not a native type",[])])

    def test_owner_private_file_strict_mode_rejects_partial_tail(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"private.gpudump"
            file.write_bytes(dump_bytes(base_records()+[(GP0,[0])]))
            with self.assertRaisesRegex(ValueError,"TRAILING_PARTIAL_NATIVE_FRAME"):
                audit_private_native_vsync(file,require_complete_vsync_end=True)
            report=audit_private_native_vsync(file)
            self.assertFalse(report["native_dump_ends_on_complete_vsync_record"])

    def test_owner_private_file_expected_frame_count_strict_mode(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"private.gpudump"
            file.write_bytes(dump_bytes())
            report=audit_private_native_vsync(file,
                expected_completed_frames=1,require_complete_vsync_end=True)
            self.assertTrue(report["independently_expected_completed_frame_count_compared"])
            with self.assertRaisesRegex(ValueError,"UNEXPECTED_COMPLETED_FRAME_COUNT"):
                audit_private_native_vsync(file,
                    expected_completed_frames=2,require_complete_vsync_end=True)

    def test_owner_private_file_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"native.gpudump"
            file.write_bytes(dump_bytes())
            link=Path(td)/"native-link.gpudump"
            link.symlink_to(file)
            with self.assertRaisesRegex(ValueError,"invalid owner-private"):
                audit_private_native_vsync(link)

    def test_metadata_does_not_contain_native_game_id_or_gpu_words(self):
        report=checked(base_records())
        encoded=json.dumps(report)
        for forbidden in ('"game_id"', '"original_gp0_words"',
                          '"prepacket_vram"', '"pixel_u16"',
                          '"original_palette_bytes"'):
            self.assertNotIn(forbidden,encoded)
        self.assertTrue(report["interpretation"][
            "all_timing_metadata_must_remain_owner_private"])


if __name__=="__main__":
    unittest.main()
