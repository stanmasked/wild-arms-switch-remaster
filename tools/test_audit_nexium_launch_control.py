#!/usr/bin/env python3
"""Synthetic no-NRO control comparison tests (no emulator is invoked)."""
import tempfile
from pathlib import Path
import unittest
from PIL import Image, ImageDraw

from audit_nexium_launch_control import diagnose, compare_screen


class ComparisonTests(unittest.TestCase):
    def test_identical_screens_resemble_each_other(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = root / "guest.png"
            second = root / "control.png"
            img = Image.new("RGB", (640, 480), (0, 0, 0))
            ImageDraw.Draw(img).rectangle((200, 100, 400, 300),
                                           fill=(44, 62, 72))
            img.save(first)
            img.save(second)
            report = diagnose(first, second, root / "comparison.json")
            self.assertEqual(report["within_16_channel_fraction"], 1.0)
            self.assertTrue(report["visually_similar_desktop"])
            self.assertTrue(report["not_emulator_gameplay_verification"])

    def test_different_game_and_desktop_not_marked_similar(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b = root / "a.png", root / "b.png"
            Image.new("RGB", (640, 480), (15, 30, 45)).save(a)
            Image.new("RGB", (640, 480), (200, 100, 85)).save(b)
            self.assertEqual(compare_screen(a, b), 0.0)
            self.assertFalse(diagnose(a, b, root / "report.json")
                             ["visually_similar_desktop"])

    def test_mismatched_dimensions_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b = root / "a.png", root / "b.png"
            Image.new("RGB", (640, 480)).save(a)
            Image.new("RGB", (800, 600)).save(b)
            with self.assertRaises(ValueError):
                compare_screen(a, b)


if __name__ == "__main__":
    unittest.main()
