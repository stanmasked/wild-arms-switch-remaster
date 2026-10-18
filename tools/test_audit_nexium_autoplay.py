#!/usr/bin/env python3
"""Synthetic screenshots for autoplay visual transition classifier."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw
from audit_nexium_autoplay import MIN_CHANGED_PIXELS, audit_frames, pixels_changed


class VisualTransitionTests(unittest.TestCase):
    def test_game_map_change_outside_fps_hud_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new = root / "old.png", root / "new.png"
            im = Image.new("RGB", (1600, 900), (13, 18, 30))
            ImageDraw.Draw(im).rectangle((370, 210, 400, 240),
                                         fill=(201, 67, 76))
            im.save(old)
            ImageDraw.Draw(im).rectangle((370, 210, 400, 240),
                                         fill=(174, 155, 115))
            ImageDraw.Draw(im).rectangle((450, 210, 480, 240),
                                         fill=(201, 67, 76))
            im.save(new)
            r = audit_frames(old, [new], root / "report.json")
            self.assertTrue(r["visual_transition_confirmed"])
            self.assertGreaterEqual(r["max_changed_pixels"], MIN_CHANGED_PIXELS)
            self.assertFalse(r["checkpoint_parity_confirmed"])

    def test_only_performance_overlay_changes_does_not_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new = root / "old.png", root / "new.png"
            im = Image.new("RGB", (1600, 900), (20, 25, 30))
            im.save(old)
            ImageDraw.Draw(im).rectangle((20, 20, 200, 100),
                                         fill=(21, 220, 20))
            im.save(new)
            r = audit_frames(old, [new], root / "report.json")
            self.assertEqual(r["max_changed_pixels"], 0)
            self.assertFalse(r["visual_transition_confirmed"])

    def test_bad_dimensions_and_duplicate_names_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = root / "a.png", root / "b.png"
            Image.new("RGB", (1600, 900)).save(a)
            Image.new("RGB", (640, 480)).save(b)
            with self.assertRaises(ValueError):
                audit_frames(a, [b], root / "report.json")
            with self.assertRaises(ValueError):
                audit_frames(a, [a], root / "report.json")

    def test_reject_invalid_threshold_crop(self):
        first = Image.new("RGB", (800, 600))
        second = Image.new("RGB", (800, 600))
        with self.assertRaises(ValueError):
            pixels_changed(first, second)


if __name__ == "__main__":
    unittest.main()
