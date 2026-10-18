#!/usr/bin/env python3
"""Synthetic image classifier tests; no emulator launch."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw
from audit_nexium_probe import analyze_shot, generate_report

COMMIT = "a" * 40
ARCHIVE = "b" * 64


class ProbeTests(unittest.TestCase):
    def test_detects_synthetic_frame_not_just_app_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guest.png"
            image = Image.new("RGB", (800, 600), (14, 20, 34))
            draw = ImageDraw.Draw(image)
            draw.rectangle((50, 70, 149, 169), fill=(47, 68, 87))
            draw.rectangle((160, 70, 259, 169), fill=(174, 155, 115))
            draw.rectangle((270, 70, 309, 109), fill=(63, 191, 138))
            draw.rectangle((320, 70, 339, 89), fill=(201, 67, 76))
            image.save(path)
            result = analyze_shot(path)
            self.assertTrue(result["synthetic_field_signature_detected"])
            self.assertGreaterEqual(result["palette_counts"]["wall"], 2000)
            output = Path(directory) / "report.json"
            report = generate_report([path], COMMIT, ARCHIVE, output)
            self.assertTrue(report["emulator_runtime_confirmed"])
            self.assertTrue(output.exists())

    def test_blank_screen_fails_even_if_image_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desktop.png"
            Image.new("RGB", (1280, 720), (18, 18, 18)).save(path)
            result = analyze_shot(path)
            self.assertFalse(result["synthetic_field_signature_detected"])
            report = generate_report([path], COMMIT, ARCHIVE,
                                     Path(directory) / "report.json")
            self.assertEqual(report["status"], "runtime_not_confirmed")
            self.assertFalse(report["emulator_runtime_confirmed"])

    def test_no_images_and_invalid_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.json"
            self.assertFalse(generate_report([], COMMIT, ARCHIVE, output)
                             ["emulator_runtime_confirmed"])
            with self.assertRaises(ValueError):
                generate_report([], "short", ARCHIVE, output)
            with self.assertRaises(ValueError):
                generate_report([], COMMIT, "0", output)

    def test_wrong_dimensions_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.png"
            Image.new("RGB", (120, 90)).save(path)
            with self.assertRaises(ValueError):
                analyze_shot(path)


if __name__ == "__main__":
    unittest.main()
