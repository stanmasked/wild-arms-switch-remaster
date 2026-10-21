"""Synthetic-only CDSTG candidate CLUT/offset audit regression tests."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdstg_color_candidates import (  # noqa: E402
    audit_cdstg_color_candidates, leading_offsets_within_region
)

STRIDE = 0x2000
GFX = 0x200
BASE = 0x80164000


def build_map(index, *, first_length=512, corrupt=None):
    data = bytearray(STRIDE)
    if index == 1:
        data[:8] = b"DUMMY!!!"
        return bytes(data)
    # Eight monotonically increasing candidate graphics pointers.
    positions = [0x100, 0x100+first_length]
    for step in (32, 32, 32, 32, 64, 128):
        positions.append(positions[-1] + step)
    for i, offset in enumerate(positions):
        struct.pack_into("<I", data, GFX + i*4, BASE+offset)
    if corrupt == "pointer":
        struct.pack_into("<I", data, GFX+4, BASE+0x080)
    start = positions[0]+GFX
    end = positions[1]+GFX
    for row in range(first_length//32):
        if row % 4 == 0:
            values = (0,)*16
        else:
            values = (0,)+(0x8000 if row%2 else 0x001F,)*15
        struct.pack_into("<16H", data, start+row*32, *values)
    # Last two sections happen to begin with bounded, ascending offsets.
    for section in (6, 7):
        start=GFX+positions[section]
        for at, value in enumerate((0, 16, 48, 80)):
            struct.pack_into("<I", data, start+at*4, value)
    if corrupt == "tail":
        data[GFX+positions[6]:GFX+positions[6]+16] = bytes(range(16))
    return bytes(data)


def analyze(payload):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"synthetic-cdstg.bin"
        path.write_bytes(payload)
        return audit_cdstg_color_candidates(
            path, map_count=3, map_bytes=STRIDE,
            gfx_offset=GFX, dummy_index=1)


class ColorCandidateAuditTests(unittest.TestCase):
    def test_regular_first_regions_and_explicit_dummy(self):
        result=analyze(build_map(0)+build_map(1)+build_map(2))
        self.assertEqual(result["ordinary_maps"], 2)
        self.assertEqual(result["first_region_multiple_of_512_count"], 2)
        self.assertEqual(result["region_5_multiple_of_32_count"], 2)
        self.assertEqual(result["maps"][1]["status"], "DUMMY_UNCLASSIFIED")
        first=result["maps"][0]
        self.assertEqual(first["first_region_color_like_16_word_rows"],16)
        self.assertEqual(first["first_region_all_zero_16_word_rows"],4)
        self.assertEqual(first["first_region_16_word_rows_beginning_zero"],16)
        self.assertEqual(first["first_region_16_word_rows_with_bit15_set"],8)
        self.assertEqual(first["first_region_unique_16_word_rows"],3)
        self.assertFalse(result["interpretation"]["original_source_bytes_emitted"])

    def test_last_two_candidate_offset_runs_not_inferred_as_tiles(self):
        result=analyze(build_map(0)+build_map(1)+build_map(2))
        regions=result["maps"][2]["final_region_offset_table_hypotheses"]
        self.assertEqual(len(regions),2)
        self.assertEqual([x["leading_internal_offset_run_count"] for x in regions],
                         [4,4])
        self.assertTrue(regions[0]["end_verified_by_next_pointer"])
        self.assertFalse(regions[1]["end_verified_by_next_pointer"])
        self.assertTrue(result["interpretation"]["internal_offset_run_not_tile_placement_proof"])

    def test_non_bank_aligned_first_region_still_reported_not_dropped(self):
        report=analyze(build_map(0,first_length=256)+
                       build_map(1)+build_map(2))
        self.assertEqual(report["first_region_multiple_of_512_count"],1)
        self.assertEqual(report["maps"][0]["first_region_color_like_16_word_rows"],8)
        self.assertFalse(report["maps"][0]["first_region_multiple_of_512"])

    def test_unordered_graphics_pointers_rejected(self):
        with self.assertRaisesRegex(ValueError,"graphics pointer run"):
            analyze(build_map(0,corrupt="pointer")+build_map(1)+build_map(2))

    def test_internal_offsets_require_strict_monotonic_alignment(self):
        self.assertEqual(leading_offsets_within_region(bytes(64)),[])
        b=bytearray(128)
        for i,v in enumerate((0,16,12,60)):
            struct.pack_into("<I",b,4*i,v)
        self.assertEqual(leading_offsets_within_region(b),[])
        struct.pack_into("<I",b,8,32)
        self.assertEqual(leading_offsets_within_region(b),[0,16,32,60])

    def test_unrelated_tail_data_does_not_become_offset_table(self):
        report=analyze(build_map(0,corrupt="tail")+
                       build_map(1)+build_map(2))
        self.assertEqual(report["maps"][0]["final_region_offset_table_hypotheses"][0]
                         ["leading_internal_offset_run_count"],0)

    def test_truncated_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"fixed records"):
            analyze((build_map(0)+build_map(1)+build_map(2))[:-1])

    def test_no_raw_palette_values_or_game_pixels_in_report(self):
        report=analyze(build_map(0)+build_map(1)+build_map(2))
        self.assertTrue(report["interpretation"]["color_words_are_bgr555_hypothesis_only"])
        self.assertNotIn("palette",report["maps"][0])
        self.assertNotIn("raw_pixels",report["maps"][0])
        self.assertIn("first_region_sha256",report["maps"][0])


if __name__ == "__main__":
    unittest.main()
