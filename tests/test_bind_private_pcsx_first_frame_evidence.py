"""Stage451 synthetic-only native first-frame GP0/VRAM/VSync joint evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bind_private_pcsx_first_frame_evidence import (
    bind_private_first_frame_capture,
    write_private_first_frame_binding_manifest,
)
from import_private_pcsx_native_gpudump import (
    GAME_ID,GP0,GP1,VSYNC,TRACE_BEGIN,
)
from test_import_private_pcsx_native_gpudump import (
    base_records,dump_bytes,
)
from test_verify_private_pcsx_native_gpudump_import import prepared,ID

def bound(native,pre,trace,**opts):
    return bind_private_first_frame_capture(native,pre,trace,**opts)


class Stage451CaptureBindingTests(unittest.TestCase):
    def test_normal_first_frame_requires_exact_native_gp0_and_vram(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            r=bound(native,pre,trace,expected_frame=449,
                    expected_native_game_id=ID,
                    expected_native_sha256=hashlib.sha256(
                        native.read_bytes()).hexdigest(),
                    expected_completed_frames=1)
            self.assertEqual(r["binding_status"],
                "WHOLE_NATIVE_CAPTURE_BOUND_TO_FIRST_FRAME_IMPORT")
            self.assertEqual(r["native_first_frame_ended_at_gpu_cycle"],1234)
            self.assertEqual(r["native_completed_frame_count"],1)
            self.assertEqual(r["imported_first_frame_packet_count"],8)
            self.assertEqual(r["imported_first_frame_live_gp0_word_count"],
                             len(base_records()[-2][1]))
            self.assertEqual(r["native_prepacket_vram_byte_count"],1048576)
            self.assertTrue(r["native_file_sha256_equal_across_all_independent_reads"])
            self.assertTrue(r["stage448_first_frame_words_match_stage449_reconstruction"])

    def test_native_dump_digest_identical_across_all_three_analyses(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            report=bound(native,pre,trace)
            self.assertEqual(report["native_dump_sha256"],
                             hashlib.sha256(native.read_bytes()).hexdigest())
            self.assertEqual(report["imported_prepacket_vram_sha256"],
                             hashlib.sha256(pre.read_bytes()).hexdigest())
            self.assertEqual(report["imported_gp0_jsonl_sha256"],
                             hashlib.sha256(trace.read_bytes()).hexdigest())

    def test_multi_frame_dump_first_frame_only_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            records=base_records()+[(GP0,[0]),(VSYNC,[5678,0])]
            native,pre,trace=prepared(td,records=records)
            r=bound(native,pre,trace,expected_completed_frames=2)
            self.assertEqual(r["native_completed_frame_count"],2)
            self.assertEqual(r["native_first_frame_ended_at_gpu_cycle"],1234)
            self.assertTrue(r["whole_native_dump_ends_at_vsync_boundary"])
            self.assertTrue(r["interpretation"][
                "first_frame_model_not_rasterized_or_proof_of_visible_texture"])

    def test_default_rejects_unfinished_native_tail_even_if_first_frame_valid(self):
        with tempfile.TemporaryDirectory() as td:
            records=base_records()+[(GP0,[0])]
            native,pre,trace=prepared(td,records=records)
            with self.assertRaisesRegex(ValueError,"complete native capture required"):
                bound(native,pre,trace)

    def test_opt_in_allows_first_frame_only_with_explicit_untrusted_tail(self):
        with tempfile.TemporaryDirectory() as td:
            records=base_records()+[(GP0,[0])]
            native,pre,trace=prepared(td,records=records)
            r=bound(native,pre,trace,require_complete_capture=False)
            self.assertEqual(r["binding_status"],
                "FIRST_FRAME_BOUND_WITH_UNVERIFIED_TRAILING_NATIVE_EVENTS")
            self.assertFalse(r["whole_native_dump_ends_at_vsync_boundary"])
            self.assertTrue(r["source_preamble_and_first_frame_crosschecked_against_native_dump"])

    def test_second_frame_timestamp_duplicate_fails_even_in_opt_in_mode(self):
        with tempfile.TemporaryDirectory() as td:
            records=base_records()+[(VSYNC,[1234,0])]
            native,pre,trace=prepared(td,records=records)
            with self.assertRaisesRegex(ValueError,"NONMONOTONIC_VSYNC_CYCLE_STAMPS"):
                bound(native,pre,trace,require_complete_capture=False)

    def test_decreasing_second_frame_timestamp_fails(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td,records=base_records()+[
                (VSYNC,[1000,0])])
            with self.assertRaisesRegex(ValueError,"not coherent"):
                bound(native,pre,trace)

    def test_expected_frame_count_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            with self.assertRaisesRegex(ValueError,"UNEXPECTED_COMPLETED_FRAME_COUNT"):
                bound(native,pre,trace,expected_completed_frames=3)

    def test_wrong_native_game_id_rejected_independently(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            with self.assertRaisesRegex(ValueError,"differs from caller"):
                bound(native,pre,trace,expected_native_game_id="SLUS-99999")

    def test_wrong_native_sha_is_rejected_independently(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            with self.assertRaisesRegex(ValueError,"independent SHA256"):
                bound(native,pre,trace,expected_native_sha256="f"*64)

    def test_wrong_operator_frame_label_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td,frame=9)
            with self.assertRaisesRegex(ValueError,"frame differs"):
                bound(native,pre,trace,expected_frame=3)

    def test_modified_initial_vram_rejected_before_chronology(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            value=bytearray(pre.read_bytes())
            value[2]=1
            pre.write_bytes(value)
            with self.assertRaisesRegex(ValueError,"VRAM differs"):
                bound(native,pre,trace)

    def test_altered_gpu_jsonl_packet_word_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            lines=trace.read_text().splitlines()
            tail=json.loads(lines[-1])
            tail["words"][-1]^=1
            lines[-1]=json.dumps(tail)
            trace.write_text("\n".join(lines)+"\n")
            with self.assertRaisesRegex(ValueError,"packet differs"):
                bound(native,pre,trace)

    def test_cross_read_mutation_of_native_dump_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            from bind_private_pcsx_first_frame_evidence import (
                preflight_private_native_gpudump)
            original=preflight_private_native_gpudump
            def incompatible(path,**kwargs):
                result=original(path,**kwargs)
                result["native_dump_sha256"]="0"*64
                return result
            with patch("bind_private_pcsx_first_frame_evidence.preflight_private_native_gpudump",
                       side_effect=incompatible),self.assertRaisesRegex(ValueError,"changed between"):
                bound(native,pre,trace)

    def test_mismatched_preflight_word_count_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            from bind_private_pcsx_first_frame_evidence import (
                preflight_private_native_gpudump)
            real=preflight_private_native_gpudump
            def changed(path,**kwargs):
                report=real(path,**kwargs)
                report["frame_summaries"][0]["gp0_word_count"]+=1
                return report
            with patch("bind_private_pcsx_first_frame_evidence.preflight_private_native_gpudump",
                       side_effect=changed),self.assertRaisesRegex(ValueError,"word count differs"):
                bound(native,pre,trace)

    def test_private_manifest_created_as_no_clobber_0600(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            r=bound(native,pre,trace)
            outfile=Path(td)/"binding.private.json"
            digest=write_private_first_frame_binding_manifest(r,outfile)
            self.assertEqual(digest,hashlib.sha256(outfile.read_bytes()).hexdigest())
            self.assertEqual(json.loads(outfile.read_text()),r)
            self.assertEqual(outfile.stat().st_mode & 0o777,0o600)
            with self.assertRaisesRegex(ValueError,"already exists"):
                write_private_first_frame_binding_manifest(r,outfile)
            self.assertEqual(digest,hashlib.sha256(outfile.read_bytes()).hexdigest())

    def test_symlink_manifest_destination_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            r=bound(native,pre,trace)
            link=Path(td)/"bad-private-manifest.json"
            link.symlink_to(native)
            with self.assertRaisesRegex(ValueError,"unsafe"):
                write_private_first_frame_binding_manifest(r,link)

    def test_invalid_strict_mode_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            with self.assertRaisesRegex(ValueError,"must be a bool"):
                bound(native,pre,trace,require_complete_capture=1)

    def test_invalid_manifest_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"private.json"
            with self.assertRaisesRegex(ValueError,"expected complete"):
                write_private_first_frame_binding_manifest({},out)
            self.assertFalse(out.exists())

    def test_report_contains_no_game_serial_source_words_or_framebuffer(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            r=bound(native,pre,trace,expected_native_game_id=ID)
            encoded=json.dumps(r)
            for forbidden in (ID,'"raw_gp0_words"','"image_pixels"',
                              '"original_palette_u16"','"cdstg_bytes"'):
                self.assertNotIn(forbidden,encoded)
            self.assertTrue(r["interpretation"][
                "all_hashes_and_metadata_must_remain_owner_private"])
            self.assertTrue(r["interpretation"][
                "source_game_scene_and_camera_not_independently_authenticated"])


if __name__=="__main__":
    unittest.main()
