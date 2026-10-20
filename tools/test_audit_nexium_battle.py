#!/usr/bin/env python3
"""Positive and adversarial synthetic inputs for real NeXium battle auditor."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H
from audit_nexium_battle import (
    audit_battle, SCREENSHOTS, BLUE, GOLD, RED, DARK, MAP_STATUS
)

PANEL = (31, 45, 66)
FIELD = (14, 20, 34)


def fake_screenshot(name):
    native = Image.new("RGB", (1280, 720), FIELD)
    d = ImageDraw.Draw(native)
    if name in ("00_field_before", "05_field_return"):
        d.rectangle((0, 0, 1279, 9), fill=MAP_STATUS)
        d.rectangle((300, 190, 360, 270), fill=(174, 155, 115))
    else:
        d.rectangle((0, 0, 1279, 719), fill=DARK)
        d.rectangle((70, 120, 609, 257), fill=PANEL)
        d.rectangle((670, 165, 1209, 328), fill=PANEL)
        d.rectangle((692, 249, 1031, 268), fill=DARK)
        width = 340 if name == "01_battle_open" else 194
        d.rectangle((692, 249, 692 + width - 1, 268), fill=RED)
        d.rectangle((670, 165, 673, 168), fill=GOLD)
        d.rectangle((70, 120, 73, 123), fill=BLUE)
        if name != "01_battle_open":
            d.rectangle((70, 284, 73, 287), fill=BLUE)
        if name == "04_after_guard":
            d.rectangle((70, 448, 73, 451), fill=BLUE)
    desktop = Image.new("RGB", SCREEN_SIZE)
    desktop.paste(
        native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST),
        (VIEW_X, 0))
    return desktop


def create_folder(path):
    for name in SCREENSHOTS:
        fake_screenshot(name).save(Path(path) / (name + ".png"))


class BattleGuestAuditTests(unittest.TestCase):
    def test_positive_six_conditions(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            result = audit_battle(root, Path(root) / "report.json")
            self.assertTrue(result["all_checks_passed"])
            self.assertEqual(len(result["checks"]), 6)

    def test_missing_frame_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            (Path(root) / "03_strike_held.png").unlink()
            with self.assertRaises(ValueError):
                audit_battle(root, Path(root) / "report.json")

    def test_extra_frame_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            fake_screenshot("01_battle_open").save(Path(root) / "extra.png")
            with self.assertRaises(ValueError):
                audit_battle(root, Path(root) / "report.json")

    def test_no_health_change_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            fake_screenshot("01_battle_open").save(
                Path(root) / "02_after_strike.png")
            result = audit_battle(root, Path(root) / "report.json")
            self.assertFalse(result["checks"]["a_strike_reduced_actual_foe_hp"])

    def test_repeated_held_strike_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            path = Path(root) / "03_strike_held.png"
            with Image.open(path) as image:
                native = image.convert("RGB")
            # Alter the inner active game region to mimic a second attack.
            # Pick a non-renderer color: the original location is red
            # in the enemy HP bar, so writing RED again is a no-op.
            native.putpixel((VIEW_X + 780, 240), (1, 255, 23))
            native.save(path)
            result = audit_battle(root, Path(root) / "report.json")
            self.assertFalse(result["checks"]["held_a_did_not_trigger_another_action"])

    def test_guard_did_not_select_third_hero(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            fake_screenshot("02_after_strike").save(
                Path(root) / "04_after_guard.png")
            result = audit_battle(root, Path(root) / "report.json")
            self.assertFalse(result["checks"]["y_guard_selected_third_hero_without_extra_hit"])

    def test_return_to_different_map_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            create_folder(root)
            path = Path(root) / "05_field_return.png"
            with Image.open(path) as image:
                desktop = image.convert("RGB")
            desktop.putpixel((VIEW_X + 600, 250), (255, 0, 255))
            desktop.save(path)
            result = audit_battle(root, Path(root) / "report.json")
            self.assertFalse(result["checks"]["b_returned_to_exact_same_field_pixels"])


if __name__ == "__main__":
    unittest.main()
