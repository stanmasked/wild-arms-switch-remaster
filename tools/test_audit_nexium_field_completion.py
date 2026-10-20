#!/usr/bin/env python3
"""Synthetic negative and positive screenshots for real 2/2 auditor."""
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from audit_nexium_checkpoints import VIEW_X, VIEW_W, VIEW_H, SCREEN_SIZE
from audit_nexium_field_journal import (
    _expected_panel, BLUE, WHITE, SPRITE_RED, EVENT_GOLD, DARK, NO_PANEL
)
from audit_nexium_field_completion import audit_completion, NAMES


def make_frame(name, bad_missing_badge=False, bad_moved_player=False,
               bad_count=False, bad_partial_player=False,
               bad_area1_counter=False, bad_second_note=False):
    native = Image.new("RGB", (1280, 720), (14, 20, 34))
    pen = ImageDraw.Draw(native)
    pen.rectangle((569, 353, 586, 370), fill=EVENT_GOLD)
    if not bad_moved_player:
        pen.rectangle((558, 278, 593, 313), fill=SPRITE_RED)
    if bad_partial_player and name == "04_completed_closed":
        # Preserve the old central red sample while corrupting nearby ink.
        pen.rectangle((580, 297, 585, 302), fill=NO_PANEL)
    if name == "04_completed_closed" and not bad_missing_badge:
        pen.rectangle((569, 353, 586, 370), fill=BLUE)
        for box in ((573, 361, 576, 364), (577, 365, 580, 368),
                    (581, 359, 584, 362), (585, 355, 586, 358)):
            pen.rectangle(box, fill=WHITE)
    if name in ("02_one_clue_open", "03_completed_open"):
        number = (1 if bad_count else 2) if name == "03_completed_open" else 1
        panel = _expected_panel(number)
        if name == "03_completed_open":
            if bad_area1_counter:
                ImageDraw.Draw(panel).rectangle((660, 140, 850, 153), fill=DARK)
            if bad_second_note:
                ImageDraw.Draw(panel).rectangle((340, 240, 590, 253), fill=DARK)
        native.paste(panel, (0, 0))
    scaled = native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    desktop = Image.new("RGB", SCREEN_SIZE, (0, 0, 0))
    desktop.paste(scaled, (VIEW_X, 0))
    return desktop


def make_folder(folder):
    for name in NAMES:
        make_frame(name).save(Path(folder) / (name + ".png"))


class CompletionPixelAuditTests(unittest.TestCase):
    def test_positive_all_six(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            report = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertTrue(report["all_checks_passed"])
            self.assertEqual(len(report["checks"]), 6)

    def test_incomplete_journal_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_frame("03_completed_open", bad_count=True).save(
                Path(tmp) / "03_completed_open.png")
            result = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertFalse(result["checks"]["full_panel_and_completion_caption_exact_two_of_two"])

    def test_one_completion_glyph_pixel_tampered(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            file = Path(tmp) / "03_completed_open.png"
            with Image.open(file) as original:
                image = original.convert("RGB")
            image.putpixel((VIEW_X + round(482 * VIEW_W / 1280),
                            round(600 * VIEW_H / 720)), (7, 8, 9))
            image.save(file)
            result = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertFalse(result["checks"]["full_panel_and_completion_caption_exact_two_of_two"])

    def test_missing_area1_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_frame("04_completed_closed", bad_missing_badge=True).save(
                Path(tmp) / "04_completed_closed.png")
            result = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertFalse(result["checks"]["second_event_full_blue_white_badge"])

    def test_player_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_frame("04_completed_closed", bad_moved_player=True).save(
                Path(tmp) / "04_completed_closed.png")
            result = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertFalse(result["checks"]["player_unchanged_by_recording_and_journal"])


    def test_corrupted_area1_progress_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_frame("03_completed_open", bad_area1_counter=True).save(
                Path(tmp) / "03_completed_open.png")
            result = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertFalse(result["all_checks_passed"])
            self.assertFalse(
                result["checks"]["full_panel_and_completion_caption_exact_two_of_two"])

    def test_missing_second_clue_note_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_frame("03_completed_open", bad_second_note=True).save(
                Path(tmp) / "03_completed_open.png")
            result = audit_completion(tmp, Path(tmp) / "report.json")
            self.assertFalse(result["all_checks_passed"])
            self.assertFalse(
                result["checks"]["full_panel_and_completion_caption_exact_two_of_two"])

    def test_player_pixel_damage_outside_old_sample_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            make_frame("04_completed_closed", bad_partial_player=True).save(
                Path(tmp) / "04_completed_closed.png")
            result = audit_completion(tmp, Path(tmp) / "report.json")
            # The original single-pixel detector would still see red.
            self.assertFalse(result["all_checks_passed"])
            self.assertFalse(
                result["checks"]["player_unchanged_by_recording_and_journal"])

    def test_missing_capture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_folder(tmp)
            (Path(tmp) / "03_completed_open.png").unlink()
            with self.assertRaises(ValueError):
                audit_completion(tmp, Path(tmp) / "report.json")


if __name__ == "__main__":
    unittest.main()
