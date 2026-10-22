"""Synthetic-only Stage438 GPU transfer/post-VRAM reconciliation tests."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_private_gp0_upload_timeline import (  # noqa: E402
    VRAM_BYTES, audit_private_gp0_upload_timeline, replay_private_gp0_clut_timeline)
from test_audit_private_gp0_upload_timeline import (  # noqa: E402
    COLORS, BANK, E6, a0, polygon, vram, vram_copy, write_trace)

def mutate_word(data, x=32, y=19):
    b=bytearray(data)
    offset=(y*1024+x)*2
    b[offset] ^= 1
    return bytes(b)


class Stage438PostframeTests(unittest.TestCase):
    def check(self, packets, final, *, start=None, required=False):
        return replay_private_gp0_clut_timeline(
            vram() if start is None else start, packets, [BANK],
            frame=12, observed_post_vram=final, require_post_match=required)

    def test_no_draw_full_memory_match(self):
        data=bytearray(vram())
        start=(19*1024+32)*2
        data[start:start+32]=COLORS
        result=self.check([E6,a0(COLORS)],bytes(data),required=True)
        verified=result["postframe_reconciliation"]
        self.assertEqual(verified["scope"],"ENTIRE_VRAM_NO_GPU_DRAW_PACKETS")
        self.assertEqual(verified["known_final_u16_word_count"],524288)
        self.assertEqual(verified["unknown_or_unmodeled_final_u16_word_count"],0)
        self.assertEqual(verified["mismatched_known_u16_word_count"],0)
        self.assertTrue(verified["all_comparable_words_match"])

    def test_no_draw_detects_any_unmodeled_byte_mutation(self):
        result=self.check([E6,a0(COLORS)],vram())
        report=result["postframe_reconciliation"]
        self.assertEqual(report["mismatched_known_u16_word_count"],15)
        self.assertFalse(report["all_comparable_words_match"])
        with self.assertRaisesRegex(ValueError,"postframe reconciliation"):
            self.check([E6,a0(COLORS)],vram(),required=True)

    def test_draw_then_upload_proves_only_16_words(self):
        data=bytearray(vram())
        start=(19*1024+32)*2
        data[start:start+32]=COLORS
        result=self.check([polygon(), E6, a0(COLORS)],bytes(data),required=True)
        report=result["postframe_reconciliation"]
        self.assertEqual(report["scope"],"EXPLICIT_TRANSFERS_AFTER_LAST_DRAW_ONLY")
        self.assertEqual(report["known_final_u16_word_count"],16)
        self.assertEqual(report["unknown_or_unmodeled_final_u16_word_count"],524288-16)
        self.assertTrue(report["all_comparable_words_match"])

    def test_draw_then_upload_known_mismatch_is_detected(self):
        data=bytearray(vram())
        start=(19*1024+32)*2
        data[start:start+32]=COLORS
        report=self.check([polygon(),E6,a0(COLORS)],
                           mutate_word(bytes(data)))["postframe_reconciliation"]
        self.assertEqual(report["known_final_u16_word_count"],16)
        self.assertEqual(report["mismatched_known_u16_word_count"],1)
        self.assertFalse(report["all_comparable_words_match"])

    def test_draw_then_upload_ignores_unmodeled_framebuffer_region(self):
        data=bytearray(vram())
        start=(19*1024+32)*2
        data[start:start+32]=COLORS
        data[0]=255
        report=self.check([polygon(),E6,a0(COLORS)],bytes(data))[
            "postframe_reconciliation"]
        self.assertEqual(report["known_final_u16_word_count"],16)
        self.assertTrue(report["all_comparable_words_match"])
        self.assertGreater(report["unknown_or_unmodeled_final_u16_word_count"],0)

    def test_upload_before_draw_does_not_prove_final_framebuffer(self):
        result=self.check([E6,a0(COLORS),polygon()],vram())
        report=result["postframe_reconciliation"]
        self.assertEqual(report["known_final_u16_word_count"],0)
        self.assertEqual(report["mismatched_known_u16_word_count"],0)
        self.assertIsNone(report["all_comparable_words_match"])
        self.assertTrue(report["no_comparable_words_means_no_verdict"])
        with self.assertRaisesRegex(ValueError,"no known comparable"):
            self.check([E6,a0(COLORS),polygon()],vram(),required=True)

    def test_copy_known_row_after_last_draw_is_comparable(self):
        data=bytearray(vram())
        start=(19*1024+64)*2
        data[start:start+32]=COLORS
        source_start=(19*1024+32)*2
        data[source_start:source_start+32]=COLORS
        result=self.check([polygon(),E6,a0(COLORS),vram_copy()],
                          bytes(data),required=True)
        report=result["postframe_reconciliation"]
        self.assertEqual(report["known_final_u16_word_count"],32)
        self.assertTrue(report["all_comparable_words_match"])

    def test_copy_stale_row_after_draw_is_not_certified(self):
        initial=vram(x=32,y=19)
        report=self.check([polygon(),E6,vram_copy()],initial,start=initial)[
            "postframe_reconciliation"]
        self.assertEqual(report["known_final_u16_word_count"],0)
        self.assertIsNone(report["all_comparable_words_match"])

    def test_no_postframe_retains_stage437_return_contract(self):
        result=replay_private_gp0_clut_timeline(vram(),[],[BANK])
        self.assertIsNone(result["postframe_reconciliation"])

    def test_reject_invalid_post_snapshot_or_boolean_contract(self):
        for raw in (b"",vram()[:-1],bytearray(vram()),"not bytes"):
            with self.subTest(item=str(type(raw))),self.assertRaises(ValueError):
                self.check([],raw)
        with self.assertRaisesRegex(ValueError,"without a postframe"):
            replay_private_gp0_clut_timeline(
                vram(),[],[BANK],require_post_match=True)
        with self.assertRaisesRegex(ValueError,"boolean"):
            replay_private_gp0_clut_timeline(
                vram(),[],[BANK],require_post_match=1)

    def test_metadata_no_raw_postframe_words(self):
        result=self.check([polygon(),E6,a0(COLORS)],vram())
        import json
        encoded=json.dumps(result)
        for forbidden in ('"palette_words"','"raw_post_vram"','"rgb_frame_pixels"',
                          '"gp0_words"'):
            self.assertNotIn(forbidden,encoded)
        self.assertTrue(result["postframe_reconciliation"][
            "gpu_drawn_pixels_and_cache_effects_unmodeled"])

    def test_integration_loads_verified_sized_private_postframe(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            initial=root/"initial.bin"
            observed=root/"after.bin"
            trace=root/"timeline.jsonl"
            initial.write_bytes(vram())
            data=bytearray(vram())
            start=(19*1024+32)*2
            data[start:start+32]=COLORS
            observed.write_bytes(data)
            write_trace(trace,[polygon(),E6,a0(COLORS)])
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[]}):
                output=audit_private_gp0_upload_timeline(
                    root/"synthetic-no-game",initial,trace,
                    observed_post_vram_path=observed,require_post_match=True)
            self.assertTrue(output["postframe_reconciliation"][
                "all_comparable_words_match"])
            self.assertEqual(output["source_map_index"],2)

    def test_integration_refuses_wrong_sized_private_post(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            initial=root/"initial.bin";initial.write_bytes(vram())
            observed=root/"after.bin";observed.write_bytes(b"short")
            trace=root/"timeline.jsonl"
            write_trace(trace,[])
            with self.assertRaisesRegex(ValueError,"exact 1MiB"):
                audit_private_gp0_upload_timeline(
                    root/"no-game",initial,trace,
                    observed_post_vram_path=observed)


if __name__=="__main__":
    unittest.main()
