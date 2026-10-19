#!/usr/bin/env python3
"""Independent invented PNG fixtures for the strict guest journal auditor."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from audit_nexium_field_journal import (
    SCREENSHOTS, GLYPHS, BLUE, DARK, WHITE, NO_PANEL, SPRITE_RED,
    EVENT_YELLOW, audit_journal,
)
from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_W, VIEW_H, VIEW_X


def glyph(draw, symbol, x, y):
    if symbol == " ":
        return
    rows = GLYPHS[symbol]
    for r, bits in enumerate(rows):
        for col in range(5):
            if bits & (1 << (4 - col)):
                draw.rectangle((x + col * 2, y + r * 2,
                                x + col * 2 + 1, y + r * 2 + 1),
                               fill=WHITE)


def journal_panel(draw, count):
    draw.rectangle((304, 80, 975, 639), fill=BLUE)
    draw.rectangle((308, 84, 971, 635), fill=DARK)
    for i, symbol in enumerate(f"CLUES {count}/2"):
        glyph(draw, symbol, 340 + 14 * i, 116)
    if count:
        for i, symbol in enumerate("A0 X4 Y1"):
            glyph(draw, symbol, 340 + 14 * i, 168)


def make_desktop(name, false_count=False, changed_player=False):
    native = Image.new("RGB", (1280, 720), NO_PANEL)
    draw = ImageDraw.Draw(native)
    if name in ("02_at_marker", "03_inspected", "06_one_closed"):
        draw.rectangle((494, 214, 529, 249), fill=SPRITE_RED)
    if name == "03_inspected":
        draw.rectangle((551, 207, 602, 211), fill=EVENT_YELLOW)
    if name == "00_empty_open":
        journal_panel(draw, 0)
    if name in ("04_one_open", "05_one_open_right_held"):
        journal_panel(draw, 0 if false_count else 1)
    if name == "06_one_closed" and changed_player:
        draw.rectangle((494, 214, 529, 249), fill=NO_PANEL)
        draw.rectangle((558, 214, 593, 249), fill=SPRITE_RED)
    projected = native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    desktop = Image.new("RGB", SCREEN_SIZE, (0, 0, 0))
    desktop.paste(projected, (VIEW_X, 0))
    return desktop


def make_folder(root):
    folder = Path(root)
    for name in SCREENSHOTS:
        make_desktop(name).save(folder / (name + ".png"))


class GuestJournalAuditTests(unittest.TestCase):
    def test_independent_positive_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            result = audit_journal(tmp, Path(tmp) / "audit.json")
            self.assertTrue(result["open_release_collect_reopen_confirmed"])
            self.assertEqual(len(result["checks"]), 7)

    def test_false_clue_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_desktop("04_one_open", false_count=True).save(
                Path(tmp) / "04_one_open.png")
            result = audit_journal(tmp, Path(tmp) / "audit.json")
            self.assertFalse(result["open_release_collect_reopen_confirmed"])
            self.assertFalse(result["checks"]["recorded_panel_exact_1_of_2"])

    def test_single_wrong_journal_pixel_is_not_masked(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            name = Path(tmp) / "04_one_open.png"
            with Image.open(name) as png:
                altered = png.convert("RGB")
            # Ordinary interior journal pixel, far from text and HUD.
            altered.putpixel((400, 240), (5, 6, 7))
            altered.save(name)
            result = audit_journal(tmp, Path(tmp) / "audit.json")
            self.assertFalse(result["open_release_collect_reopen_confirmed"])
            self.assertFalse(result["checks"]["recorded_panel_exact_1_of_2"])

    def test_player_moved_while_journal_held_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_desktop("06_one_closed", changed_player=True).save(
                Path(tmp) / "06_one_closed.png")
            result = audit_journal(tmp, Path(tmp) / "audit.json")
            self.assertFalse(result["open_release_collect_reopen_confirmed"])
            self.assertFalse(
                result["checks"]["journal_released_and_player_did_not_move"])

    def test_missing_and_wrong_dimensions_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            (Path(tmp) / "02_at_marker.png").unlink()
            with self.assertRaises(ValueError):
                audit_journal(tmp, Path(tmp) / "audit.json")
            Image.new("RGB", (80, 60)).save(
                Path(tmp) / "02_at_marker.png")
            with self.assertRaises(ValueError):
                audit_journal(tmp, Path(tmp) / "audit.json")


if __name__ == "__main__":
    unittest.main()
