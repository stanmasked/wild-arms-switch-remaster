"""Synthetic-only genuine-format 32/64KiB CDFLR/CDSTG LZSS tests."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdstg_map_lzss import audit_map_lzss  # noqa: E402

STRIDE = 0x6000
GRAPHICS_START = 0x200
GB = 0x80164000


def compressed_zeros(expected):
    if expected not in (0x8000, 0x10000):
        raise ValueError("invalid synthetic length")
    token_list = [bytes((0, 15))] * (expected // 18)
    if expected % 18:
        token_list.append(bytes((0, expected % 18 - 3)))
    data = bytearray(struct.pack("<I", expected))
    for pos in range(0, len(token_list), 8):
        data.append(0)  # LSB-first dictionary-ref flags
        for token in token_list[pos:pos + 8]:
            data.extend(token)
    return bytes(data)


def make_map(map_index, *, expected=0x8000, truncate=False,
             extra_trailing=0, invalid_pointer=False,
             unknown_header=False):
    block = bytearray(STRIDE)
    if map_index == 1:
        block[:7] = b"DUMMY!!"
        return bytes(block)
    comp = compressed_zeros(expected)
    if truncate:
        comp = comp[:11]
    if unknown_header:
        comp = struct.pack("<I", 1234) + comp[4:]
    padded = len(comp) + ((-len(comp)) % 4) + extra_trailing
    starts = [0x100, 0x200, 0x200 + padded]
    for i, value in enumerate(starts):
        struct.pack_into("<I", block, GRAPHICS_START + i * 4,
                         GB + value)
    if invalid_pointer:
        struct.pack_into("<I", block, GRAPHICS_START, GB + 4)
    block[GRAPHICS_START + starts[1]:GRAPHICS_START + starts[1] + len(comp)] = comp
    return bytes(block)


def scan(payload, **kwargs):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic-cdstg.bin"
        path.write_bytes(payload)
        return audit_map_lzss(path, map_bytes=STRIDE,
                              graphics_offset=GRAPHICS_START,
                              map_count=3, dummy_index=1, **kwargs)


class MapLZSSTests(unittest.TestCase):
    def test_32_and_64_kib_decoded_with_exact_pointer_boundaries(self):
        report = scan(make_map(0) + make_map(1) +
                      make_map(2, expected=0x10000))
        self.assertEqual(report["candidate_0x8000_0x10000_prefix_count"], 2)
        self.assertEqual(report["exactly_decoded_pointer_bounded_stream_count"], 2)
        self.assertEqual(report["decoded_output_byte_count_histogram"],
                         {"0x8000": 1, "0x10000": 1})
        self.assertEqual(report["per_map"][1]["status"], "DUMMY_NOT_SCANNED")
        self.assertTrue(all(0 <= s["alignment_bytes"] <= 3
                            for s in report["decoded_stream_fingerprints"]))
        self.assertTrue(report["interpretation"]["no_original_decompressed_bytes_emitted"])

    def test_truncated_marker_like_block_is_not_misreported_as_valid(self):
        report = scan(make_map(0, truncate=True) +
                      make_map(1) + make_map(2))
        self.assertEqual(report["exactly_decoded_pointer_bounded_stream_count"], 1)
        self.assertEqual(report["not_verified_candidates"][0]["map_index"], 0)
        self.assertEqual(report["not_verified_candidates"][0]["classification"],
                         "DECODE_REJECTED")

    def test_extra_trailing_bytes_invalidate_encoded_region_match(self):
        report = scan(make_map(0, extra_trailing=8) +
                      make_map(1) + make_map(2))
        self.assertEqual(report["exactly_decoded_pointer_bounded_stream_count"], 1)
        self.assertEqual(report["not_verified_candidates"][0]["classification"],
                         "BOUNDARY_MISMATCH")

    def test_unrelated_prefix_does_not_claim_lzss(self):
        report = scan(make_map(0, unknown_header=True) +
                      make_map(1) + make_map(2))
        self.assertEqual(report["candidate_0x8000_0x10000_prefix_count"], 1)
        self.assertEqual(report["not_verified_candidates"], [])

    def test_invalid_initial_graphics_pointer_rejected(self):
        with self.assertRaisesRegex(ValueError, "graphics pointer run"):
            scan(make_map(0, invalid_pointer=True) +
                 make_map(1) + make_map(2))

    def test_partial_source_and_wrong_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, "fixed-record"):
            scan((make_map(0) + make_map(1) + make_map(2))[:-1])

    def test_dummy_source_does_not_accidentally_trigger_decode(self):
        report = scan(make_map(0, unknown_header=True) +
                      make_map(1) + make_map(2, unknown_header=True))
        self.assertEqual(report["exactly_decoded_pointer_bounded_stream_count"], 0)
        self.assertEqual(report["skipped_dummy_map_index"], 1)

    def test_same_decompressed_zero_pixels_same_digest_across_maps(self):
        report = scan(make_map(0) + make_map(1) + make_map(2))
        hashes = [x["decoded_sha256"]
                  for x in report["decoded_stream_fingerprints"]]
        self.assertEqual(len(hashes), 2)
        self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
