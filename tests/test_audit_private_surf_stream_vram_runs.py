"""Stage440 ROM-free decoded-stream vs raw VRAM byte-run tests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_private_surf_stream_vram_runs import (  # noqa: E402
    BLOCK_BYTES, VRAM_BYTES, match_decoded_stream_runs,
    audit_private_surf_stream_vram)


def data_blocks(count=4, *, seed=1):
    # Distinct high-information 64-byte blocks; not commercial content.
    return b"".join(bytes((seed + block*41 + i) % 256 for i in range(64))
                    for block in range(count))


def stream(data, index=6):
    return {"decoded":data,"graphics_region_index":index}


def make_vram(data=b"", *, x_words=64, y=10):
    out=bytearray(VRAM_BYTES)
    if data:
        start=y*2048+x_words*2
        out[start:start+len(data)]=data
    return bytes(out)


def run(streams, vram):
    return match_decoded_stream_runs(streams,vram)


class Stage440StreamVRAMRunTests(unittest.TestCase):
    def test_four_contiguous_blocks_on_aligned_vram_scanline(self):
        original=data_blocks(4)
        report=run([stream(original)],make_vram(original))
        self.assertEqual(report["confirmed_byte_identical_run_count"],1)
        entry=report["run_samples"][0]
        self.assertEqual(entry["candidate_stream_ordinal"],0)
        self.assertEqual(entry["graphics_region_index"],6)
        self.assertEqual(entry["source_offset_bytes"],0)
        self.assertEqual((entry["vram_x_words"],entry["vram_y"]),(64,10))
        self.assertEqual(entry["exact_contiguous_block_count"],4)
        self.assertEqual(entry["exact_byte_span"],256)
        self.assertEqual(entry["byte_span_sha256"],hashlib.sha256(original).hexdigest())

    def test_two_matching_blocks_rejected_by_default(self):
        original=data_blocks(4)
        report=run([stream(original)],make_vram(original[:128]))
        self.assertEqual(report["confirmed_byte_identical_run_count"],0)
        self.assertGreater(report["candidate_anchor_hit_count"],0)

    def test_three_matching_blocks_at_nonzero_source_offset(self):
        original=data_blocks(5)
        suffix=original[64:64+192]
        report=run([stream(original)],make_vram(suffix))
        self.assertEqual(report["confirmed_byte_identical_run_count"],1)
        self.assertEqual(report["run_samples"][0]["source_offset_bytes"],64)
        self.assertEqual(report["run_samples"][0]["exact_byte_span"],192)

    def test_low_information_zero_block_excluded_not_counted_as_anchor(self):
        original=bytes(64)+data_blocks(3)
        report=run([stream(original)],make_vram(original))
        self.assertGreaterEqual(report["source_low_information_anchor_exclusions"],1)
        self.assertEqual(report["confirmed_byte_identical_run_count"],1)
        self.assertEqual(report["run_samples"][0]["source_offset_bytes"],64)

    def test_repeated_high_diversity_pattern_fanout_rejected(self):
        repeated=data_blocks(1)*17
        report=run([stream(repeated)],make_vram(repeated))
        self.assertEqual(report["distinct_eligible_anchor_count"],0)
        self.assertEqual(report["source_high_fanout_anchor_exclusions"],17)
        self.assertEqual(report["confirmed_byte_identical_run_count"],0)

    def test_run_at_final_valid_vram_scanline_position(self):
        original=data_blocks(3)
        result=run([stream(original)],
                   make_vram(original,x_words=928,y=511))
        self.assertEqual(result["confirmed_byte_identical_run_count"],1)
        self.assertEqual(result["run_samples"][0]["vram_x_words"],928)
        self.assertEqual(result["run_samples"][0]["vram_y"],511)

    def test_no_crossing_vram_row_even_if_bytes_continue(self):
        original=data_blocks(4)
        # 3 blocks would cross VRAM row boundary from 1920 bytes onward.
        result=run([stream(original)],make_vram(original,x_words=960,y=50))
        self.assertEqual(result["confirmed_byte_identical_run_count"],0)

    def test_unaligned_vram_offset_not_misreported(self):
        original=data_blocks(3)
        result=run([stream(original)],make_vram(original,x_words=65,y=10))
        self.assertEqual(result["confirmed_byte_identical_run_count"],0)

    def test_duplicate_candidate_streams_are_not_claimed_unique(self):
        original=data_blocks(3)
        result=run([stream(original,6),stream(original,8)],
                   make_vram(original))
        self.assertEqual(result["confirmed_byte_identical_run_count"],2)
        self.assertEqual(
            {i["graphics_region_index"] for i in result["run_samples"]},
            {6,8})

    def test_stream_decode_geometry_rejected(self):
        invalid=(b"", b"partial", data_blocks(3)[:-1],
                 data_blocks(1025))
        for data in invalid:
            with self.subTest(length=len(data)),self.assertRaises(ValueError):
                run([stream(data)],bytes(VRAM_BYTES))
        with self.assertRaises(ValueError):
            run([{"decoded":data_blocks(3),"graphics_region_index":True}],
                bytes(VRAM_BYTES))

    def test_vram_length_type_and_limits_rejected(self):
        original=data_blocks(3)
        for raw in (bytes(VRAM_BYTES-1),bytearray(VRAM_BYTES),b""):
            with self.subTest(raw_type=type(raw)),self.assertRaises(ValueError):
                run([stream(original)],raw)
        for kwargs in (
            {"minimum_contiguous_blocks":1},{"minimum_contiguous_blocks":33},
            {"minimum_distinct_bytes":65},{"minimum_nonzero_bytes":0},
            {"max_run_samples":0},{"max_run_samples":257},
            {"minimum_contiguous_blocks":True}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                match_decoded_stream_runs([stream(original)],
                                          bytes(VRAM_BYTES),**kwargs)

    def test_one_block_only_never_counted_regardless_of_occurrence(self):
        original=data_blocks(3)
        partial=make_vram(original[:64])
        report=run([stream(original)],partial)
        self.assertEqual(report["confirmed_byte_identical_run_count"],0)

    def test_sample_cap_keeps_full_match_count(self):
        original=data_blocks(3)
        memory=bytearray(VRAM_BYTES)
        for y in (2,4,6):
            start=y*2048+128
            memory[start:start+192]=original
        report=match_decoded_stream_runs(
            [stream(original)],bytes(memory),max_run_samples=1)
        self.assertEqual(report["confirmed_byte_identical_run_count"],3)
        self.assertEqual(report["reported_run_sample_count"],1)
        self.assertTrue(report["run_samples_truncated"])

    def test_source_block_different_by_one_byte_does_not_match(self):
        original=data_blocks(3)
        altered=bytearray(original)
        altered[80] ^= 1
        result=run([stream(original)],make_vram(bytes(altered)))
        self.assertEqual(result["confirmed_byte_identical_run_count"],0)

    def test_binary_privacy_metadata_is_byte_free(self):
        original=data_blocks(4)
        report=run([stream(original)],make_vram(original))
        stored=json.dumps(report)
        for forbidden in ('"raw_texture_bytes"','"source_decoded"',
                          '"original_palette_words"','"pixel_rgba"'):
            self.assertNotIn(forbidden,stored)
        self.assertTrue(report["interpretation"][
            "matched_run_does_not_prove_a_gp0_transfer_or_visible_draw"])
        self.assertTrue(report["interpretation"]["metadata_hashes_remain_owner_private"])

    def test_private_entrypoint_uses_only_synthetic_source_dependencies(self):
        original=data_blocks(4)
        with tempfile.TemporaryDirectory() as tmp:
            data_path=Path(tmp)/"private_vram.u16le.bin"
            data_path.write_bytes(make_vram(original))
            with patch("audit_private_surf_stream_vram_runs.read_private_candidates",
                       return_value={
                           "map_index":2,
                           "candidate_banks":[bytes(512)],
                           "graphics_pointer_count":9,
                           "verified_streams":[stream(original)]}):
                report=audit_private_surf_stream_vram(
                    "synthetic-not-real-CDSTG.BIN",data_path)
            self.assertEqual(report["private_palette_bank_count"],1)
            self.assertEqual(report["map_index"],2)
            self.assertEqual(report["confirmed_byte_identical_run_count"],1)
            self.assertTrue(report["private_decoded_streams_not_emitted"])

    def test_private_input_missing_or_wrong_size_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"short.bin"
            path.write_bytes(b"tiny")
            with self.assertRaisesRegex(ValueError,"exact 1048576"):
                audit_private_surf_stream_vram("none",path)


if __name__ == "__main__":
    unittest.main()
