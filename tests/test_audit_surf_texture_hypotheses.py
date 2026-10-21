"""Synthetic-only Surf Village texture-layout hypothesis tests.

Never includes original Wild Arms source bytes or game images.
"""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_surf_texture_hypotheses import (  # noqa: E402
    audit_surf_layout, pixel_layout_hypotheses,
)

STRIDE = 0x6000
GFX = 0x200
GRAPHICS_BASE = 0x80164000


def compress_zero_stream(expected):
    tokens = [bytes((0, 15))] * (expected // 18)
    if expected % 18:
        tokens.append(bytes((0, (expected % 18) - 3)))
    out = bytearray(struct.pack("<I", expected))
    for i in range(0, len(tokens), 8):
        out.append(0)
        out.extend(b"".join(tokens[i:i+8]))
    return bytes(out)


def map_fixture(index, *, output_bytes=0x8000,
                corrupt=None):
    block = bytearray(STRIDE)
    if index == 1:
        block[:7] = b"DUMMY!!"
        return bytes(block)
    src = compress_zero_stream(output_bytes)
    if corrupt == "truncated":
        src = src[:12]
    padded = len(src) + (-len(src)) % 4
    starts = [0x100, 0x200, 0x200+padded]
    for i, addr in enumerate(starts):
        struct.pack_into("<I", block, GFX+i*4, GRAPHICS_BASE+addr)
    if corrupt == "first_pointer":
        struct.pack_into("<I", block, GFX, GRAPHICS_BASE+0x200)
    block[GFX+starts[1]:GFX+starts[1]+len(src)] = src
    return bytes(block)


def scan(blob, map_index=2):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/"synthetic-cdstg.bin"
        path.write_bytes(blob)
        return audit_surf_layout(path, map_index=map_index,
                                 map_bytes=STRIDE,
                                 graphics_offset=GFX,
                                 map_count=3, dummy_map_index=1)


class SurfLayoutHypothesesTests(unittest.TestCase):
    def test_decodes_synthetic_32_kib_without_claiming_texture_geometry(self):
        r = scan(map_fixture(0) + map_fixture(1) + map_fixture(2))
        self.assertEqual(r["graphics_pointer_count"], 3)
        self.assertEqual(r["verified_lzss_regions"], 1)
        self.assertEqual(r["next_pointer_bounded_regions"], 2)
        s = r["verified_streams"][0]
        self.assertEqual(s["decoded_bytes"], 32768)
        self.assertEqual(s["region_index"], 1)
        self.assertEqual(s["distinct_byte_values"], 1)
        self.assertEqual(s["fraction_of_zero_nibbles"], 1.0)
        self.assertEqual(len(s["candidate_layouts"]), 7)
        self.assertTrue(r["interpretation"]["candidate_dimensions_not_proven"])
        self.assertFalse(r["interpretation"]["game_source_pixels_emitted"])

    def test_64_kib_has_different_8bpp_geometry_options(self):
        r = scan(map_fixture(0) + map_fixture(1) +
                 map_fixture(2, output_bytes=0x10000))
        s = r["verified_streams"][0]
        self.assertEqual(s["decoded_bytes"], 65536)
        self.assertEqual(len(s["candidate_layouts"]), 8)
        self.assertTrue(any(x["assumed_bits_per_pixel"] == 8 and
                            x["assumed_width"] == 256 and
                            x["assumed_height"] == 256
                            for x in s["candidate_layouts"]))

    def test_low_nibble_first_hypothesis_is_explicated(self):
        samples = pixel_layout_hypotheses(bytes([0x21])*32768)
        self.assertEqual(len(samples), 7)
        view = next(x for x in samples if x["assumed_bits_per_pixel"] == 4
                    and x["assumed_width"] == 256)
        self.assertEqual(view["used_index_values"], 2)
        self.assertEqual(view["assumed_height"], 256)
        self.assertEqual(view["horizontal_neighbor_equal_ratio"], 0.0)

    def test_rejected_truncated_candidate_fails_closed(self):
        r = scan(map_fixture(0) + map_fixture(1) +
                 map_fixture(2, corrupt="truncated"))
        self.assertEqual(r["verified_lzss_regions"], 0)
        self.assertEqual(r["rejected_header_like_regions"][0]["region_index"], 1)

    def test_corrupt_graphics_pointer_table_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "graphics pointer table"):
            scan(map_fixture(0) + map_fixture(1) +
                 map_fixture(2, corrupt="first_pointer"))

    def test_dummy_map_is_not_a_texture_candidate(self):
        with self.assertRaisesRegex(ValueError, "dummy"):
            scan(map_fixture(0) + map_fixture(1) + map_fixture(2), map_index=1)

    def test_truncated_container_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "fixed-map geometry"):
            scan((map_fixture(0) + map_fixture(1) + map_fixture(2))[:-1])

    def test_no_raw_pixel_or_palette_fields_are_emitted(self):
        r = scan(map_fixture(0) + map_fixture(1) + map_fixture(2))
        for s in r["verified_streams"]:
            self.assertNotIn("decoded_pixel_bytes", s)
            self.assertNotIn("palette_values", s)
            self.assertIn("decoded_sha256", s)


if __name__ == "__main__":
    unittest.main()
