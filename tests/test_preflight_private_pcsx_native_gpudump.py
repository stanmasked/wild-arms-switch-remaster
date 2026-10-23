"""Stage448 ROM-free native GPUDUMP preflight coverage and privacy."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from preflight_private_pcsx_native_gpudump import (
    summarize_private_native_gpudump,preflight_private_native_gpudump,
)
from import_private_pcsx_native_gpudump import (
    GP0,GP1,VSYNC,READBACK,THROWAWAY,TRACE_BEGIN,GPU_VERSION,
)
from test_import_private_pcsx_native_gpudump import (
    base_records,dump_bytes,files,
)


class Stage448PreflightTests(unittest.TestCase):
    def test_supported_synthetic_frame_preflight_passes_without_exporting_payload(self):
        report=summarize_private_native_gpudump(dump_bytes())
        self.assertTrue(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertEqual(report["first_frame_import_diagnostic"],
                         "SUPPORTED_MODELED_FIRST_FRAME")
        self.assertEqual(report["completed_native_frame_count"],1)
        self.assertEqual(report["frame_summaries"][0]["gp0_transport_record_count"],1)
        self.assertEqual(report["native_record_type_counts"]["VSYNC_records"],1)

    def test_full_vram_initialization_not_counted_as_live_gpu_frame_bytes(self):
        report=summarize_private_native_gpudump(dump_bytes())
        bootstrap=report["bootstrap_type_counts"]
        self.assertEqual(bootstrap["GP0_records"],2)
        self.assertGreater(bootstrap["GP0_words"],260000)
        self.assertLess(report["frame_summaries"][0]["gp0_word_count"],100)
        self.assertTrue(report["interpretation"][
            "bootstrap_full_vram_is_not_original_live_frame_traffic"])

    def test_unmodeled_first_frame_gpu_gp1_detected_without_leaking_words(self):
        records=base_records()
        records.insert(-1,(GP1,[0x0800aabb]))
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertIn("unsupported live GP1",report["first_frame_import_diagnostic"])
        self.assertEqual(report["frame_summaries"][0]["gp1_word_count"],1)
        self.assertTrue(report["frame_summaries"][0][
            "unsupported_live_gpu_side_events_present"])
        self.assertNotIn('"live_gp1_words"',json.dumps(report))
        self.assertNotIn('"raw_gp1_payload"',json.dumps(report))

    def test_unmodeled_live_gpu_readback_rejected_by_importer_but_preflight_succeeds(self):
        records=base_records()
        records.insert(-1,(READBACK,[55]))
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertEqual(report["frame_summaries"][0]["readback_record_count"],1)
        self.assertIn("unsupported live",report["first_frame_import_diagnostic"])

    def test_unmodeled_live_throwaway_rejected(self):
        records=base_records()
        records.insert(-1,(THROWAWAY,[1]))
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertEqual(report["frame_summaries"][0]["throwaway_record_count"],1)

    def test_unmodeled_gp0_opcode_yields_diagnostic_only(self):
        # GP0(02) is now modeled; keep diagnostic-only handling of GP0(40).
        records=base_records(live=[0x40000000,0,0])
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertIn("unsupported GP0 opcode",report["first_frame_import_diagnostic"])
        self.assertTrue(report["interpretation"][
            "first_frame_compatibility_only_not_emulator_attestation"])

    def test_unmodeled_gpu_commands_in_second_frame_do_not_invalidate_first(self):
        records=base_records()
        records.extend([(GP1,[0x08000002]),(VSYNC,[5678,0])])
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertTrue(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertEqual(report["completed_native_frame_count"],2)
        self.assertTrue(report["frame_summaries"][1][
            "unsupported_live_gpu_side_events_present"])

    def test_vsync_count_and_frame_summary_cap_distinguished(self):
        records=base_records()+[(VSYNC,[2000,0]),(VSYNC,[3000,0])]
        report=summarize_private_native_gpudump(
            dump_bytes(records),max_frame_summaries=1)
        self.assertEqual(report["completed_native_frame_count"],3)
        self.assertEqual(report["sampled_frame_count"],1)
        self.assertTrue(report["frame_samples_truncated"])

    def test_open_trailing_frame_is_not_claimed_complete(self):
        records=base_records()+[(GP0,[0])]
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertEqual(report["completed_native_frame_count"],1)
        self.assertEqual(report["open_trailing_frame_events"]["GP0_words"],1)
        self.assertTrue(report["first_frame_import_accepted_by_stage447_subset"])

    def test_missing_tracebegin_is_incomplete_without_bypassing_checks(self):
        records=[rec for rec in base_records() if rec[0]!=TRACE_BEGIN]
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertEqual(report["first_frame_import_diagnostic"],
                         "NO_NATIVE_TRACE_BEGIN")
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertEqual(report["completed_native_frame_count"],0)

    def test_empty_first_live_gpu_frame_is_not_falsely_importable(self):
        records=base_records()
        records.pop(-2)  # remove only live GP0
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])
        self.assertIn("missing completed first live frame",
                      report["first_frame_import_diagnostic"])

    def test_split_native_transport_record_is_not_double_counted_as_gp0_packet(self):
        records=base_records()
        words=records[-2][1]
        records[-2:-1]=[(GP0,words[:5]),(GP0,words[5:])]
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertEqual(report["frame_summaries"][0]["gp0_transport_record_count"],2)
        self.assertTrue(report["first_frame_import_accepted_by_stage447_subset"])

    def test_duplicate_tracebegin_remains_error_in_compatibility_diagnostic(self):
        records=base_records()
        records.insert(-1,(TRACE_BEGIN,[]))
        report=summarize_private_native_gpudump(dump_bytes(records))
        self.assertEqual(report["frame_summaries"][0]["repeated_trace_begin_count"],1)
        self.assertFalse(report["first_frame_import_accepted_by_stage447_subset"])

    def test_invalid_native_binary_framing_is_rejected_not_summarized(self):
        with self.assertRaises(ValueError):
            summarize_private_native_gpudump(dump_bytes()[:-2])

    def test_private_file_entrypoint_rejects_symlinks_and_bad_sizes(self):
        with tempfile.TemporaryDirectory() as td:
            src,_,_=files(td)
            report=preflight_private_native_gpudump(src)
            self.assertTrue(report["first_frame_import_accepted_by_stage447_subset"])
            link=Path(td)/"symlink.gpudump"
            link.symlink_to(src)
            with self.assertRaises(ValueError):
                preflight_private_native_gpudump(link)
            src.write_bytes(b"small")
            with self.assertRaises(ValueError):
                preflight_private_native_gpudump(src)

    def test_frame_summary_limits_reject_boolean_and_overly_large(self):
        for limit in (True,0,65):
            with self.subTest(limit=limit),self.assertRaises(ValueError):
                summarize_private_native_gpudump(dump_bytes(),max_frame_summaries=limit)

    def test_metadata_never_contains_game_id_raw_vram_or_gpu_payload(self):
        result=summarize_private_native_gpudump(dump_bytes())
        serialized=json.dumps(result,sort_keys=True)
        for forbidden in ('"game_id"','"vram_pixels"',
                          '"raw_gpu_words"','"payload_u32"' ):
            self.assertNotIn(forbidden,serialized)
        self.assertTrue(result["interpretation"][
            "no_original_gpu_words_vram_image_game_id_or_pixels_emitted"])
        self.assertTrue(result["interpretation"][
            "native_dump_and_all_metadata_must_remain_private"])


if __name__=="__main__":
    unittest.main()
