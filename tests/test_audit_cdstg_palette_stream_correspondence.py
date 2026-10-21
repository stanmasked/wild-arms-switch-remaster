"""Synthetic-only tests of candidate 512-byte bank / true WA1 stream counts."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdstg_palette_stream_correspondence import (
    audit_bank_stream_correspondence,
)

MAP_SIZE = 0x5000
GFX_OFFSET = 0x200
BASE = 0x80164000


def packed_zeroes(length):
    tokens = [bytes((0, 15))] * (length // 18)
    if length % 18:
        tokens.append(bytes((0, length % 18 - 3)))
    output = bytearray(struct.pack("<I", length))
    for start in range(0, len(tokens), 8):
        output.append(0)
        output.extend(b"".join(tokens[start:start+8]))
    return bytes(output)


def fake_map(index, *, banks=2, corrupt_second=False,
             bad_pointer=False, dummy=False):
    block = bytearray(MAP_SIZE)
    if dummy:
        block[:7] = b"DUMMY!!"
        return bytes(block)
    a, b = packed_zeroes(0x8000), packed_zeroes(0x10000)
    if corrupt_second:
        b = b[:16]
    align_a = (-len(a)) % 4
    align_b = (-len(b)) % 4
    # first region (candidate palette banks), non-LZSS spacer,
    # two *strictly bounded* LZSS items, and unbounded final region.
    starts = [0x100, 0x100+int(banks*512)]
    starts += [starts[-1]+32]
    starts += [starts[-1]+len(a)+align_a]
    starts += [starts[-1]+len(b)+align_b]
    if starts[-1] + 4 > MAP_SIZE - GFX_OFFSET:
        raise AssertionError("synthetic map insufficient size")
    for number, offset in enumerate(starts):
        struct.pack_into("<I", block, GFX_OFFSET+number*4, BASE+offset)
    if bad_pointer:
        struct.pack_into("<I", block, GFX_OFFSET, BASE+0x180)
    block[GFX_OFFSET+starts[2]:GFX_OFFSET+starts[2]+len(a)] = a
    block[GFX_OFFSET+starts[3]:GFX_OFFSET+starts[3]+len(b)] = b
    # deterministic bank bytes, without copyrighted pixels
    for i in range(int(banks*512)):
        block[GFX_OFFSET+0x100+i] = (i+index) % 251
    return bytes(block)


def scan(m0, m2):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"synthetic-cdstg.bin"
        path.write_bytes(m0 + fake_map(1, dummy=True) + m2)
        return audit_bank_stream_correspondence(
            path, map_bytes=MAP_SIZE, gfx_start=GFX_OFFSET,
            map_count=3, dummy_index=1)


class BankStreamCorrelationTests(unittest.TestCase):
    def test_matching_two_banks_two_real_decoded_streams(self):
        report = scan(fake_map(0), fake_map(2))
        self.assertEqual(report["count_match_map_count"], 2)
        self.assertEqual(report["extra_bank_map_count"], 0)
        self.assertEqual(report["maps"][1]["status"], "DUMMY_UNCLASSIFIED")
        row = report["maps"][0]
        self.assertEqual(row["candidate_512_byte_banks"], 2)
        self.assertEqual(row["verified_lzss_region_count"], 2)
        self.assertEqual(row["candidate_lzss_region_indices"], [2, 3])
        self.assertEqual(row["classification"], "COUNT_MATCH")
        self.assertTrue(report["interpretation"]["bank_ordinal_to_stream_ordinal_not_verified"])
        self.assertTrue(report["interpretation"]["no_original_pixels_or_color_values_emitted"])

    def test_extra_bank_is_not_silently_discarded(self):
        report = scan(fake_map(0), fake_map(2, banks=3))
        self.assertEqual(report["count_match_map_count"], 1)
        self.assertEqual(report["extra_bank_map_count"], 1)
        self.assertEqual(report["mismatching_map_indices"], [2])
        self.assertEqual(report["maps"][2]["count_difference"], 1)

    def test_invalid_second_lzss_reduces_verified_count(self):
        report = scan(fake_map(0), fake_map(2, corrupt_second=True))
        self.assertEqual(report["maps"][2]["verified_lzss_region_count"], 1)
        self.assertEqual(report["maps"][2]["candidate_512_byte_banks"], 2)
        self.assertEqual(report["extra_bank_map_count"], 1)

    def test_non_bank_aligned_first_region_is_reported_not_as_palette(self):
        report = scan(fake_map(0), fake_map(2, banks=1.5))
        self.assertEqual(report["unaligned_bank_map_count"], 1)
        self.assertIsNone(report["maps"][2]["candidate_512_byte_banks"])

    def test_invalid_first_pointer_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "graphics pointer run|first graphics region"):
            scan(fake_map(0, bad_pointer=True), fake_map(2))

    def test_bad_fixed_geometry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"synthetic"
            path.write_bytes(fake_map(0)[:-1])
            with self.assertRaisesRegex(ValueError, "exact fixed-length"):
                audit_bank_stream_correspondence(
                    path, map_bytes=MAP_SIZE, gfx_start=GFX_OFFSET,
                    map_count=1, dummy_index=0)
            with self.assertRaisesRegex(ValueError, "invalid map count"):
                audit_bank_stream_correspondence(
                    path, map_bytes=MAP_SIZE, gfx_start=GFX_OFFSET,
                    map_count=0, dummy_index=0)

    def test_no_palette_inference_from_count_match(self):
        report = scan(fake_map(0), fake_map(2))
        self.assertEqual(report["count_match_map_count"], 2)
        self.assertTrue(report["interpretation"]["candidate_palette_rows_not_verified_vram_cluts"])
        self.assertTrue(report["maps"][0]["per_bank_palette_assignment_unverified"])


if __name__ == "__main__":
    unittest.main()
