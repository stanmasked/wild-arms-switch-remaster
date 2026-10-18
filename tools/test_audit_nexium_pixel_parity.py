#!/usr/bin/env python3
"""Invented screenshots verify the exact projected RGB comparison gate."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from audit_field_capture import NAMES
from audit_nexium_checkpoints import refs, desktop
from audit_nexium_pixel_parity import (
    VIEW_W, VIEW_H, VISIBLE_PIXELS, audit_all, compare_scene,
)


def make_projected_fixture(root):
    root = Path(root)
    ref = root / "reference"
    obs = root / "observed"
    refs(ref)
    obs.mkdir()
    for name in NAMES:
        image = desktop(ref / (name + ".png"))
        # NeXium overlays a running chart over the game's upper-left
        # background, completely independent from the guest pixels.
        ImageDraw.Draw(image).rectangle((23, 0, 242, 153),
                                        fill=(13, 248, 44))
        image.save(obs / (name + ".png"))
    return ref, obs


class ProjectedPixelParityTests(unittest.TestCase):
    def test_five_projected_references_are_byte_exact_outside_hud(self):
        with tempfile.TemporaryDirectory() as folder:
            ref, obs = make_projected_fixture(folder)
            report = audit_all(ref, obs, Path(folder) / "result.json")
            self.assertTrue(report["all_five_projected_visible_rgb_match"])
            self.assertEqual(report["visible_pixels_compared_total"],
                             VISIBLE_PIXELS * 5)
            self.assertEqual(report["mismatched_visible_pixels_total"], 0)
            self.assertEqual(report["hud_pixels_excluded_total"], 220 * 154 * 5)
            self.assertFalse(report["native_1280x720_gpu_framebuffer_captured"])

    def test_single_changed_game_pixel_fails_even_with_matching_hud(self):
        with tempfile.TemporaryDirectory() as folder:
            ref, obs = make_projected_fixture(folder)
            image_path = obs / (NAMES[2] + ".png")
            with Image.open(image_path) as image:
                image.load()
                altered = image.convert("RGB")
            altered.putpixel((600, 330), (5, 7, 9))
            altered.save(image_path)
            result = audit_all(ref, obs, Path(folder) / "result.json")
            self.assertFalse(result["all_five_projected_visible_rgb_match"])
            self.assertEqual(result["mismatched_visible_pixels_total"], 1)

    def test_hud_changes_do_not_affect_image_parity(self):
        with tempfile.TemporaryDirectory() as folder:
            ref, obs = make_projected_fixture(folder)
            image_path = obs / (NAMES[0] + ".png")
            with Image.open(image_path) as image:
                altered = image.convert("RGB")
            ImageDraw.Draw(altered).rectangle((30, 25, 230, 145),
                                               fill=(140, 50, 190))
            altered.save(image_path)
            result = compare_scene(ref / (NAMES[0] + ".png"), image_path)
            self.assertTrue(result["exact_visible_rgb_match"])

    def test_malformed_reference_and_missing_screen_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            ref, obs = make_projected_fixture(folder)
            (obs / (NAMES[3] + ".png")).unlink()
            with self.assertRaises(ValueError):
                audit_all(ref, obs, Path(folder) / "failed.json")
            (ref / (NAMES[1] + ".png")).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                audit_all(ref, obs, Path(folder) / "failed.json")


if __name__ == "__main__":
    unittest.main()
