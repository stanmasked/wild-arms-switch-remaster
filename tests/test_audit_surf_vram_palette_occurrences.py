"""ROM-free, synthetic-only tests for Stage427 Surf Village VRAM evidence."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from audit_surf_vram_palette_occurrences import (  # noqa: E402
    VRAM_BYTES, VRAM_WIDTH_WORDS, _row_filter,
    match_palette_rows_to_private_vram,
)
from test_audit_surf_palette_rows import (  # noqa: E402
    GRAPHICS, RECORD, map_record,
)

GEOMETRY = {
    "map_count": 3,
    "map_bytes": RECORD,
    "graphics_offset": GRAPHICS,
    "dummy_index": 1,
}
COLORS = struct.pack("<16H", 0, 0x001F, 0x03E0, 0x7C00,
                     *([0x7FFF] * 12))


def put_words(vram, x, y, raw=COLORS):
    offset = (y * VRAM_WIDTH_WORDS + x) * 2
    vram[offset:offset+len(raw)] = raw


def make_report(vram, *, cdstg_records=None, **options):
    if cdstg_records is None:
        cdstg_records = (map_record(0), map_record(1), map_record(2))
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        disc = folder/"synthetic_cdstg.bin"
        memory = folder/"synthetic_vram.bin"
        disc.write_bytes(b"".join(cdstg_records))
        memory.write_bytes(vram)
        return match_palette_rows_to_private_vram(
            disc, memory, map_index=2, **GEOMETRY, **options)


class SurfVramCandidateEvidenceTests(unittest.TestCase):
    def test_exact_grid_aligned_match_is_metadata_not_a_clut_claim(self):
        vram = bytearray(VRAM_BYTES)
        put_words(vram, 16, 12)
        report = make_report(vram)
        self.assertEqual(report["candidate_row_count"], 32)
        self.assertEqual(report["eligible_byte_distinct_row_count"], 1)
        self.assertEqual(report["eligible_bank_row_reference_count"], 2)
        self.assertEqual(report["excluded_all_zero_rows"], 2)
        self.assertEqual(report["excluded_low_distinct_nonzero_rows"], 28)
        self.assertEqual(report["rows_with_at_least_one_memory_occurrence"], 1)
        row = report["candidate_rows"][0]
        self.assertEqual(row["matching_grid_position_count"], 1)
        self.assertEqual(row["matching_grid_position_sample"],
                         [{"x_words": 16, "y": 12}])
        self.assertEqual(row["candidate_bank_row_references"], [
            {"candidate_bank_index": 0, "candidate_row_index": 0},
            {"candidate_bank_index": 1, "candidate_row_index": 0},
        ])
        self.assertTrue(report["interpretation"][
            "exact_grid_occurrences_are_not_verified_clut_use"])

    def test_no_match_without_original_candidate_bytes_in_vram(self):
        report = make_report(bytes(VRAM_BYTES))
        self.assertEqual(report["rows_with_at_least_one_memory_occurrence"], 0)
        self.assertEqual(report["candidate_rows"][0]["matching_grid_position_count"], 0)

    def test_reject_offset_not_on_sixteen_word_clut_grid(self):
        vram = bytearray(VRAM_BYTES)
        put_words(vram, 17, 30)
        report = make_report(vram)
        self.assertEqual(report["rows_with_at_least_one_memory_occurrence"], 0)

    def test_reject_palette_that_crosses_vram_row_boundary(self):
        vram = bytearray(VRAM_BYTES)
        put_words(vram, 1016, 31)
        report = make_report(vram)
        self.assertEqual(report["rows_with_at_least_one_memory_occurrence"], 0)

    def test_bit15_difference_is_not_ignored_in_exact_matching(self):
        vram = bytearray(VRAM_BYTES)
        changed = bytearray(COLORS)
        struct.pack_into("<H", changed, 2, 0x801F)
        put_words(vram, 32, 20, changed)
        report = make_report(vram)
        self.assertEqual(report["rows_with_at_least_one_memory_occurrence"], 0)

    def test_capped_position_sample_does_not_understate_total_count(self):
        vram = bytearray(VRAM_BYTES)
        for x,y in ((0,3),(16,3),(32,3),(48,3)):
            put_words(vram, x, y)
        report = make_report(vram, max_position_samples=2)
        row = report["candidate_rows"][0]
        self.assertEqual(row["matching_grid_position_count"], 4)
        self.assertEqual(row["matching_grid_position_sample"], [
            {"x_words": 0, "y": 3}, {"x_words": 16, "y": 3}])
        self.assertTrue(row["position_sample_truncated"])

    def test_all_zero_and_low_information_rows_do_not_create_false_hits(self):
        self.assertEqual(_row_filter(bytes(32), 3), "ALL_ZERO")
        self.assertEqual(_row_filter(struct.pack("<16H", 0, *([7]*15)), 3),
                         "LOW_DISTINCT_NONZERO")
        self.assertIsNone(_row_filter(COLORS, 3))
        self.assertEqual(_row_filter(COLORS, 5), "LOW_DISTINCT_NONZERO")
        report = make_report(bytes(VRAM_BYTES), minimum_distinct_nonzero=5)
        self.assertEqual(report["eligible_byte_distinct_row_count"], 0)

    def test_wrong_vram_byte_length_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly 1024x512"):
            make_report(bytes(VRAM_BYTES-1))
        with self.assertRaisesRegex(ValueError, "exactly 1024x512"):
            make_report(bytes(VRAM_BYTES+1))

    def test_bad_parameters_fail_closed(self):
        for kwargs in ({"minimum_distinct_nonzero": 0},
                       {"minimum_distinct_nonzero": True},
                       {"max_position_samples": 0},
                       {"max_position_samples": 65}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    make_report(bytes(VRAM_BYTES), **kwargs)

    def test_untrusted_cdstg_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, "length"):
            make_report(bytes(VRAM_BYTES), cdstg_records=(
                map_record(0), map_record(1), map_record(2)[:-1]))

    def test_report_never_contains_original_palette_or_vram_bytes(self):
        vram = bytearray(VRAM_BYTES)
        put_words(vram, 1008, 511)
        report = make_report(vram)
        self.assertEqual(report["candidate_rows"][0][
            "matching_grid_position_sample"], [{"x_words": 1008, "y": 511}])
        self.assertEqual(len(report["vram_sha256"]), 64)
        serialized = json.dumps(report)
        for secret_field in ("raw_vram", "raw_palette", "decoded_pixels",
                             "palette_words", "vram_bytes", "screenshot"):
            self.assertNotIn('"' + secret_field + '":', serialized)
        flags = report["interpretation"]
        self.assertTrue(flags["raw_vram_and_palette_words_not_exported"])
        self.assertTrue(flags["palette_bank_to_stream_assignment_unverified"])
        self.assertTrue(flags["no_original_framebuffer_comparison"])


if __name__ == "__main__":
    unittest.main()
