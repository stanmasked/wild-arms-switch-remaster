"""Stage510: fail-closed RGB witness for visually ambiguous PNG metadata.

All PNGs are synthetic, generated in memory. No private game pixels or source
material are required or published by this test.
"""
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from decode_private_opaque_rgb_png import (
    VISUAL_TRANSFORM_CHUNKS, decode_private_opaque_rgb_png,
)


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def synthetic_png(*, color=2, before=(), after=()):
    channels=3 if color==2 else 4
    expected=bytes((248, 0, 0, 255) if channels==4 else (248, 0, 0))
    header=struct.pack(">IIBBBBB", 1, 1, 8, color, 0, 0, 0)
    # 8-bit RGB/RGBA, 1x1, PNG filter zero.
    raster=b"\x00" + expected
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + b"".join(chunk(k, v) for k, v in before)
            + chunk(b"IDAT", zlib.compress(raster))
            + b"".join(chunk(k, v) for k, v in after)
            + chunk(b"IEND", b""))


class StrictFrameWitnessPngTests(unittest.TestCase):
    def test_synthetic_profile_free_rgb_and_opaque_rgba_are_supported(self):
        for color in (2, 6):
            with self.subTest(color=color):
                size, rgb=decode_private_opaque_rgb_png(synthetic_png(color=color))
                self.assertEqual(size, (1, 1))
                self.assertEqual(rgb, bytes((248, 0, 0)))

    def test_benign_text_metadata_is_not_rejected(self):
        dimensions, rgb=decode_private_opaque_rgb_png(
            synthetic_png(before=((b"tEXt", b"label\x00synthetic"),)))
        self.assertEqual(dimensions, (1, 1))
        self.assertEqual(rgb, bytes((248, 0, 0)))

    def test_visual_transform_chunks_are_explicitly_listed(self):
        expected={
            b"gAMA", b"cHRM", b"iCCP", b"sRGB", b"cICP", b"mDCv",
            b"cLLi", b"sBIT", b"eXIf", b"bKGD", b"acTL", b"fcTL", b"fdAT",
            b"pHYs", b"oFFs", b"sCAL", b"pCAL", b"sTER",
        }
        self.assertEqual(VISUAL_TRANSFORM_CHUNKS, expected)

    def test_color_profile_hdr_exif_and_background_are_rejected(self):
        payloads={
            b"gAMA":struct.pack(">I", 45455),
            b"cHRM":bytes(32),
            b"iCCP":b"synthetic\x00\x00" + zlib.compress(b"profile"),
            b"sRGB":b"\x00",
            b"cICP":bytes((1, 13, 0, 1)),
            b"mDCv":bytes(24),
            b"cLLi":bytes(8),
            b"sBIT":bytes((8, 8, 8)),
            b"eXIf":b"MM\x00*\x00\x00\x00\x08",
            b"bKGD":bytes(6),
        }
        for kind, payload in payloads.items():
            with self.subTest(kind=kind), self.assertRaisesRegex(
                    ValueError, "visual-transform metadata"):
                decode_private_opaque_rgb_png(
                    synthetic_png(before=((kind, payload),)))

    def test_visual_geometry_rejected_on_both_sides_of_idat(self):
        for kind in (b"pHYs", b"oFFs", b"sCAL", b"pCAL", b"sTER"):
            for side in ("before", "after"):
                with self.subTest(kind=kind, side=side):
                    with self.assertRaisesRegex(ValueError, "visual-transform"):
                        decode_private_opaque_rgb_png(
                            synthetic_png(**{side: ((kind, b"data"),)}))

    def test_unrecognized_ancillary_chunk_is_rejected(self):
        for location in ("before", "after"):
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, "unrecognized ancillary"):
                    decode_private_opaque_rgb_png(
                        synthetic_png(**{location: ((b"vpAg", b"data"),)}))

    def test_animation_chunks_rejected_before_and_after_idat(self):
        payloads={
            b"acTL":struct.pack(">II", 2, 0),
            b"fcTL":bytes(26),
            b"fdAT":bytes(8),
        }
        for kind, payload in payloads.items():
            for before in (True, False):
                with self.subTest(kind=kind, before=before):
                    kw={"before" if before else "after":((kind, payload),)}
                    with self.assertRaisesRegex(ValueError, "animation unsupported"):
                        decode_private_opaque_rgb_png(synthetic_png(**kw))

    def test_profile_metadata_does_not_become_safe_in_rgba_mode(self):
        for kind in (b"sRGB", b"gAMA", b"acTL"):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                    ValueError, "unsupported for exact raw RGB witness"):
                decode_private_opaque_rgb_png(
                    synthetic_png(color=6, before=((kind, b"\x00"*8),)))

    def test_cropped_or_malformed_metadata_crc_does_not_bypass_validation(self):
        original=synthetic_png(before=((b"gAMA", bytes(4)),))
        mutated=original.replace(b"gAMA", b"gAMB", 1)
        with self.assertRaisesRegex(ValueError, "CRC"):
            decode_private_opaque_rgb_png(mutated)


if __name__=="__main__":
    unittest.main()
