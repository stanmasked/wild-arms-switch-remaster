#!/usr/bin/env python3
"""Adversarial synthetic fixtures for NeXium real-guest battle RGB gate."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from audit_nexium_battle import SHOTS, audit_battle
from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H


def fixtures(root):
    root = Path(root)
    refs, frames = root / "host", root / "guest"
    refs.mkdir()
    frames.mkdir()
    native0 = Image.new("RGB", (1280, 720), (24, 40, 66))
    ImageDraw.Draw(native0).rectangle((440, 160, 830, 590),
                                      fill=(211, 45, 86))
    native1 = native0.copy()
    ImageDraw.Draw(native1).rectangle((710, 220, 802, 330),
                                      fill=(26, 217, 67))
    native0.save(refs / "battle-preview-initial.png")
    native1.save(refs / "battle-preview-strike.png")
    field = Image.new("RGB", (1280, 720), (130, 153, 97))
    ImageDraw.Draw(field).rectangle((460, 230, 550, 290),
                                     fill=(67, 53, 199))
    sources = [field, native0, native1, field, native0]
    for name, frame in zip(SHOTS, sources):
        screen = Image.new("RGB", SCREEN_SIZE)
        screen.paste(frame.resize((VIEW_W, VIEW_H),
                                  Image.Resampling.NEAREST), (VIEW_X, 0))
        ImageDraw.Draw(screen).rectangle((VIEW_X, 0, VIEW_X + 219, 153),
                                         fill=(93, 20, 159))
        screen.save(frames / (name + ".png"))
    return refs, frames


class BattleGuestAuditTests(unittest.TestCase):
    def test_exact_route_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            result = audit_battle(ref, shots, Path(tmp) / "result.json")
            self.assertTrue(result["all_checks_passed"])
            self.assertEqual(len(result["checks"]), 6)
            self.assertEqual(
                result["battle_strike"]["mismatched_visible_pixels"], 0)

    def test_held_battle_frame_does_not_count_as_strike(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            (shots / "02_battle_strike.png").write_bytes(
                (shots / "01_battle_open.png").read_bytes())
            result = audit_battle(ref, shots, Path(tmp) / "result.json")
            self.assertFalse(result["all_checks_passed"])
            self.assertFalse(result["checks"]["strike_after_A_exact_host_RGB"])
            self.assertFalse(result["checks"]["strike_visibly_changed_battle"])

    def test_single_bad_visible_pixel_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            path = shots / "02_battle_strike.png"
            with Image.open(path) as original:
                frame = original.convert("RGB")
            frame.putpixel((850, 450), (1, 2, 3))
            frame.save(path)
            result = audit_battle(ref, shots, Path(tmp) / "result.json")
            self.assertFalse(result["checks"]["strike_after_A_exact_host_RGB"])
            self.assertEqual(
                result["battle_strike"]["mismatched_visible_pixels"], 1)

    def test_wrong_return_to_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            (shots / "03_field_return.png").write_bytes(
                (shots / "01_battle_open.png").read_bytes())
            result = audit_battle(ref, shots, Path(tmp) / "result.json")
            self.assertFalse(result["checks"]["field_restored_after_B_exact_RGB"])

    def test_reopen_does_not_reset_combat_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            (shots / "04_battle_reopen.png").write_bytes(
                (shots / "02_battle_strike.png").read_bytes())
            result = audit_battle(ref, shots, Path(tmp) / "result.json")
            self.assertFalse(
                result["checks"]["battle_reopened_after_R_exact_initial_RGB"])

    def test_hud_variation_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            path = shots / "01_battle_open.png"
            with Image.open(path) as original:
                frame = original.convert("RGB")
            ImageDraw.Draw(frame).rectangle((30, 20, 220, 145),
                                             fill=(0, 255, 255))
            frame.save(path)
            result = audit_battle(ref, shots, Path(tmp) / "result.json")
            self.assertTrue(result["all_checks_passed"])

    def test_missing_and_excess_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            (shots / "04_battle_reopen.png").unlink()
            with self.assertRaises(ValueError):
                audit_battle(ref, shots, Path(tmp) / "result.json")
            (shots / "extra.png").write_bytes(b"not a screenshot")
            with self.assertRaises(ValueError):
                audit_battle(ref, shots, Path(tmp) / "result.json")

    def test_wrong_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref, shots = fixtures(tmp)
            Image.new("RGB", (400, 300), (42, 44, 46)).save(
                shots / "00_field_before.png")
            with self.assertRaises(ValueError):
                audit_battle(ref, shots, Path(tmp) / "result.json")


if __name__ == "__main__":
    unittest.main()
