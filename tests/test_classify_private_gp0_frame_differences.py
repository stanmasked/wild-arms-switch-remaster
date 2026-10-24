"""Stage529 synthetic-only VRAM discrepancy classifier regression tests."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from classify_private_gp0_frame_differences import (
    classify_vram_differences,VRAM_BYTES,VRAM_W,
)


def blank(): return bytearray(VRAM_BYTES)


def put(a,x,y,pixel):
    struct.pack_into("<H",a,2*(y*VRAM_W+x),pixel)


def audit(a,b,c,roi=(2,2,12,10)):
    return classify_vram_differences(bytes(a),bytes(b),bytes(c),roi=roi)


class Stage529SyntheticDiagnostics(unittest.TestCase):
    def test_same_three_buffers_have_no_differences(self):
        x=blank();put(x,3,3,0x801f)
        s=audit(x,x,x)
        self.assertEqual(s["observed_vs_modeled_u16_mismatches"],0)
        self.assertEqual(s["authentic_observed_words_different_from_initial"],0)
        self.assertEqual(s["best_five_bounded_shift_candidates"][0]["mismatches"],0)

    def test_decomposes_rgb_error_and_mask_bit_only_mismatch(self):
        a,b,c=blank(),blank(),blank()
        put(b,4,4,0x001f);put(c,4,4,0x801f)
        put(b,5,4,0x03e0)
        put(c,6,4,0x7c00)
        r=audit(a,b,c)
        self.assertEqual(r["observed_vs_modeled_u16_mismatches"],3)
        self.assertEqual(r["category_counts"]["high_bit_only_mismatch"],1)
        self.assertEqual(r["category_counts"]["model_zero_observed_nonzero"],1)
        self.assertEqual(r["category_counts"]["model_nonzero_observed_zero"],1)
        self.assertEqual(r["rgb555_channel_absolute_error_sums"],[0,31,31])

    def test_shift_by_one_detected_as_heuristic(self):
        a,b,c=blank(),blank(),blank()
        for y in range(5,9):
            for x in range(5,10):
                value=(x*19+y*17)&0x7fff
                put(b,x,y,value)
                put(c,x+1,y,value)
        r=audit(a,b,c,roi=(4,4,8,6))
        self.assertGreater(r["observed_vs_modeled_u16_mismatches"],0)
        self.assertEqual(r["best_five_bounded_shift_candidates"][0],
                         {"dx":1,"dy":0,"mismatches":0})

    def test_original_equal_player_but_candidate_mismatches(self):
        a,b,c=blank(),blank(),blank()
        put(a,4,4,0x1234);put(b,4,4,0x1234)
        put(c,4,4,0x4321)
        r=audit(a,b,c)
        self.assertEqual(r["authentic_observed_words_different_from_initial"],0)
        self.assertEqual(r["observed_vs_modeled_u16_mismatches"],1)
        self.assertEqual(r["category_counts"]["different_nonzero_colors"],1)

    def test_reject_wrong_size_malformed_region_and_mutable_source(self):
        a,b,c=blank(),blank(),blank()
        for incorrect in (b"",bytes(VRAM_BYTES-2),a):
            with self.subTest(type=type(incorrect)),self.assertRaises(ValueError):
                classify_vram_differences(
                    incorrect,bytes(b),bytes(c),roi=(2,2,4,4))
        for roi in ((0,0,4,4),(2,2,0,4),(2,2,600,600),
                    (1001,501,22,10),(2,2,1.5,3),[2,2,4,4]):
            with self.subTest(roi=roi),self.assertRaises(ValueError):
                audit(a,b,c,roi)

    def test_result_contains_no_raw_pixels_or_game_hashes(self):
        a,b,c=blank(),blank(),blank()
        put(c,4,4,0x1234)
        result=audit(a,b,c)
        self.assertEqual(result["schema"],1)
        self.assertNotIn("pixels",result)
        self.assertTrue(result["pixel_arrays_and_game_content_never_serialized"])
        self.assertTrue(result["shift_candidates_are_heuristics_not_uv_proof"])


if __name__=="__main__":
    unittest.main()
