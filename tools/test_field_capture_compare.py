#!/usr/bin/env python3
"""Synthetic-only fixtures. These tests do not launch an emulator."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from audit_field_capture import NAMES, png_chunk
from compare_field_emulator_png import (
    compare_capture, pixel_differences, read_png_rgb
)


def encode_png(width, height, rgb, channels=3, filter_type=0):
    row_length = width * channels
    scanlines = bytearray()
    last = bytes(row_length)
    for y in range(height):
        row = rgb[y * row_length:(y + 1) * row_length]
        scanlines.append(filter_type)
        for i, value in enumerate(row):
            a = row[i - channels] if i >= channels else 0
            b = last[i]
            c = last[i - channels] if i >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = a
            elif filter_type == 2:
                predictor = b
            elif filter_type == 3:
                predictor = (a + b) // 2
            else:
                p = a + b - c
                distances = [abs(p - a), abs(p - b), abs(p - c)]
                predictor = [a, b, c][distances.index(min(distances))]
            scanlines.append((value - predictor) & 255)
        last = row
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB",
                      width, height, 8, 2 if channels == 3 else 6, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(bytes(scanlines)))
    png += png_chunk(b"IEND", b"")
    return png


class DecoderTests(unittest.TestCase):
    def test_all_png_filters(self):
        raw = bytes([10, 20, 30, 40, 50, 60, 70, 80, 90,
                     90, 80, 70, 60, 50, 40, 30, 20, 10])
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "sample.png"
            for mode in range(5):
                file.write_bytes(encode_png(3, 2, raw, filter_type=mode))
                self.assertEqual((3, 2, raw), read_png_rgb(file, (3, 2)))

    def test_rgba_ignores_alpha(self):
        rgba = bytes([10, 20, 30, 0, 40, 50, 60, 255])
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "rgba.png"
            file.write_bytes(encode_png(2, 1, rgba, channels=4))
            self.assertEqual(bytes([10, 20, 30, 40, 50, 60]),
                             read_png_rgb(file, (2, 1))[2])

    def test_reject_crc_dimensions_and_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "bad.png"
            good = encode_png(2, 1, bytes([1, 2, 3, 4, 5, 6]))
            file.write_bytes(good[:-4])
            with self.assertRaises(ValueError):
                read_png_rgb(file, (2, 1))
            file.write_bytes(good)
            with self.assertRaises(ValueError):
                read_png_rgb(file, (1280, 720))
            corrupt = bytearray(good)
            corrupt[30] ^= 0x10
            file.write_bytes(corrupt)
            with self.assertRaises(ValueError):
                read_png_rgb(file, (2, 1))

    def test_pixel_threshold(self):
        a = bytes([10, 20, 30, 40, 50, 60])
        b = bytes([10, 22, 30, 44, 50, 60])
        self.assertEqual(pixel_differences(a, b, 0)[:2], (2, 4))
        self.assertEqual(pixel_differences(a, b, 2)[:2], (1, 4))
        self.assertEqual(pixel_differences(a, b, 4)[:2], (0, 4))


class ComparisonTests(unittest.TestCase):
    def setup_fixture(self, base):
        ref = base / "ref"
        observed = base / "observed"
        ref.mkdir()
        observed.mkdir()
        records = []
        for i, name in enumerate(NAMES):
            rgb = bytes([i, 10, 20, i + 1, 30, 40])
            contents = encode_png(2, 1, rgb)
            (ref / (name + ".png")).write_bytes(contents)
            (observed / (name + ".png")).write_bytes(contents)
            records.append({
                "scene": name,
                "png_sha256": hashlib.sha256(contents).hexdigest(),
                "raw_rgb_sha256": hashlib.sha256(rgb).hexdigest(),
            })
        manifest = base / "manifest.json"
        manifest.write_text(json.dumps({
            "kind": "host_reference_not_emulator_capture",
            "width": 2, "height": 1, "round_trip_pixels_equal": True,
            "frames": records}), encoding="utf-8")
        return ref, observed, manifest

    def test_matching_and_different_captures(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            ref, obs, manifest = self.setup_fixture(base)
            report_path = base / "report.json"
            ok = compare_capture(ref, obs, manifest, report_path,
                                 expected_size=(2, 1))
            self.assertEqual(ok["result"], "pass")
            self.assertTrue(report_path.exists())
            self.assertEqual(ok["observed_capture_provenance"],
                             "not_verified_by_this_tool")
            (obs / (NAMES[1] + ".png")).write_bytes(
                encode_png(2, 1, bytes([1, 20, 20, 2, 30, 40])))
            different = compare_capture(ref, obs, manifest, report_path,
                                        expected_size=(2, 1))
            self.assertEqual(different["result"], "mismatch")
            self.assertEqual(different["frames"][1]["changed_pixels"], 1)
            accepted = compare_capture(
                ref, obs, manifest, report_path,
                expected_size=(2, 1), max_changed_pixels=1)
            self.assertEqual(accepted["result"], "pass")

    def test_ref_mismatch_and_same_path_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            ref, obs, manifest = self.setup_fixture(base)
            report = base / "report.json"
            with self.assertRaises(ValueError):
                compare_capture(ref, ref, manifest, report,
                                expected_size=(2, 1))
            (ref / (NAMES[0] + ".png")).write_bytes(
                encode_png(2, 1, bytes([99, 10, 20, 1, 30, 40])))
            with self.assertRaises(ValueError):
                compare_capture(ref, obs, manifest, report,
                                expected_size=(2, 1))


if __name__ == "__main__":
    unittest.main()
