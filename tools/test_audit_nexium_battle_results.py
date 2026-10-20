#!/usr/bin/env python3
"""Adversarial synthetic fixture test for the independent real-ZL guest oracle."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, screen_point
from audit_nexium_battle_results import audit_history, NAMES, MAP, GOLD, BLUE, WHITE, PANEL

DARK = (12, 19, 31)
BACKGROUND = (14, 20, 34)
RED = (201, 67, 76)


def screenshot(name):
    native = Image.new("RGB", (1280, 720), BACKGROUND)
    d = ImageDraw.Draw(native)
    if name in ("02_first_battle", "06_next_battle"):
        d.rectangle((0, 0, 1279, 719), fill=DARK)
        d.rectangle((68, 215, 76, 226), fill=BLUE)
        d.rectangle((918, 246, 927, 252), fill=RED)
        if name == "06_next_battle":
            d.rectangle((227, 688, 232, 693), fill=GOLD)
    else:
        d.rectangle((0, 0, 1279, 9), fill=MAP)
        d.rectangle((340, 230, 370, 250), fill=RED)
        if name in ("01_zl_empty", "04_zl_retreat"):
            d.rectangle((690, 612, 1239, 707), fill=PANEL)
            d.rectangle((690, 612, 1239, 615), fill=GOLD)
            if name == "01_zl_empty":
                d.rectangle((787, 679, 790, 684), fill=WHITE)
            else:
                d.rectangle((791, 679, 796, 684), fill=WHITE)
                d.rectangle((921, 677, 925, 682), fill=WHITE)
    desktop = Image.new("RGB", SCREEN_SIZE)
    desktop.paste(native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST),
                  (VIEW_X, 0))
    return desktop


def write_set(folder):
    for name in NAMES:
        screenshot(name).save(Path(folder) / (name + ".png"))


def tamper(im, x, y, color):
    X, Y = screen_point(x, y)
    ImageDraw.Draw(im).rectangle((X-1, Y-1, X+1, Y+1), fill=color)


class BattleHistoryAuditTests(unittest.TestCase):
    def assert_rejects(self, name, x, y, color, check):
        with tempfile.TemporaryDirectory() as folder:
            write_set(folder)
            path = Path(folder) / (name + ".png")
            with Image.open(path) as original:
                im = original.convert("RGB")
            tamper(im, x, y, color)
            im.save(path)
            result = audit_history(folder, Path(folder)/"audit.json")
            self.assertFalse(result["checks"][check])

    def test_all_seven_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            write_set(folder)
            result = audit_history(folder, Path(folder)/"audit.json")
            self.assertTrue(result["all_checks_passed"], result["checks"])
            self.assertEqual(len(result["sha256"]), 7)

    def test_emulator_fps_hud_does_not_obscure_bottom_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            write_set(folder)
            path = Path(folder)/"04_zl_retreat.png"
            with Image.open(path) as original:
                im = original.convert("RGB")
            ImageDraw.Draw(im).rectangle((13, 14, 238, 153),
                                         fill=(60, 212, 92))
            im.save(path)
            self.assertTrue(audit_history(
                folder, Path(folder)/"audit.json")["all_checks_passed"])

    def test_requires_real_zero_record(self):
        self.assert_rejects("01_zl_empty", 789, 681, PANEL,
                            "ZL_renders_zero_retreat_count_on_same_field")

    def test_requires_exact_one_retreat(self):
        self.assert_rejects("04_zl_retreat", 793, 681, PANEL,
                            "next_ZL_panel_shows_exactly_one_retreat")

    def test_requires_retreat_not_none_glyph(self):
        self.assert_rejects("04_zl_retreat", 923, 679, PANEL,
                            "next_ZL_panel_shows_exactly_one_retreat")

    def test_cannot_fake_first_battle_border(self):
        self.assert_rejects("02_first_battle", 70, 220, DARK,
                            "R_opens_first_combat_without_previous_history")

    def test_next_battle_has_carried_history(self):
        self.assert_rejects("06_next_battle", 230, 691, DARK,
                            "new_battle_retains_record_with_fresh_combat")

    def test_no_overlay_when_ZL_is_released(self):
        self.assert_rejects("05_zl_released", 700, 615, GOLD,
                            "releasing_ZL_restores_the_exact_original_field")

    def test_missing_and_extra_screenshots_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            write_set(folder)
            Path(folder, "03_field_after_retreat.png").unlink()
            with self.assertRaises(ValueError):
                audit_history(folder, Path(folder)/"audit.json")
            screenshot("03_field_after_retreat").save(
                Path(folder)/"03_field_after_retreat.png")
            screenshot("03_field_after_retreat").save(Path(folder)/"extra.png")
            with self.assertRaises(ValueError):
                audit_history(folder, Path(folder)/"audit.json")


if __name__ == "__main__":
    unittest.main()
