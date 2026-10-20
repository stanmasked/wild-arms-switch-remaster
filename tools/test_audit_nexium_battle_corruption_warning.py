#!/usr/bin/env python3
"""Synthetic banner fixtures; real evidence is captured by Stage369 NeXium."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import SCREEN_SIZE, screen_point
from audit_nexium_battle_corruption_warning import (
    HELD, IDLE, SAMPLES, GOLD, RED, audit_warning,
)


def fixture(folder):
    root = Path(folder)
    shots = root / "guest"
    shots.mkdir()
    clean = Image.new("RGB", SCREEN_SIZE, (20, 30, 40))
    warning = clean.copy()
    for x, y, color in SAMPLES:
        warning.putpixel(screen_point(x, y), color)
    warning.putpixel(screen_point(690, 612), GOLD)
    for name in HELD:
        warning.save(shots / (name + ".png"))
    for name in IDLE:
        clean.save(shots / (name + ".png"))
    prior = root / "valid_rewards.png"
    clean.save(prior)
    return shots, prior, root / "audit.json"


class WarningGuestAuditTests(unittest.TestCase):
    def test_positive_strict_neXium_warning(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit_warning(*fixture(d))
            self.assertTrue(result["all_checks_passed"], result["checks"])
            self.assertEqual(len(result["checks"]), 8)

    def test_wrong_crc_red_accent_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            path = a[0] / (HELD[0] + ".png")
            with Image.open(path) as im:
                f = im.convert("RGB")
            f.putpixel(screen_point(690, 554), (245, 183, 66))
            f.save(path)
            self.assertFalse(audit_warning(*a)["checks"][
                "twentythird_initial_ZL_shows_corrupt_A_B_notice"])

    def test_warning_does_not_disappear_after_B(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            with Image.open(a[0] / (IDLE[0]+".png")) as im:
                frame = im.convert("RGB")
            for x, y, color in SAMPLES:
                frame.putpixel(screen_point(x, y), color)
            frame.save(a[0] / (IDLE[0]+".png"))
            self.assertFalse(audit_warning(*a)["checks"][
                "both_normal_B_return_frames_have_no_warning"])

    def test_valid_game_must_not_show_false_error(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            with Image.open(a[1]) as im:
                frame = im.convert("RGB")
            for x, y, color in SAMPLES:
                frame.putpixel(screen_point(x, y), color)
            frame.save(a[1])
            self.assertFalse(audit_warning(*a)["checks"][
                "prior_valid_four_win_reward_panel_has_no_warning"])

    def test_banner_change_between_sessions_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            path = a[0] / (HELD[3]+".png")
            with Image.open(path) as im:
                frame = im.convert("RGB")
            frame.putpixel(screen_point(800, 570), RED)
            frame.save(path)
            self.assertFalse(audit_warning(*a)["checks"][
                "banner_static_through_both_processes"])

    def test_warning_must_not_cover_results(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            path = a[0] / (HELD[2]+".png")
            with Image.open(path) as im:
                frame = im.convert("RGB")
            frame.putpixel(screen_point(690, 612), RED)
            frame.save(path)
            self.assertFalse(audit_warning(*a)["checks"][
                "prior_ZL_results_outline_uncovered"])

    def test_missing_or_extra_frame_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            (a[0] / (HELD[0]+".png")).unlink()
            with self.assertRaises(ValueError):
                audit_warning(*a)
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            Image.new("RGB", SCREEN_SIZE).save(a[0] / "extra.png")
            with self.assertRaises(ValueError):
                audit_warning(*a)


if __name__ == "__main__":
    unittest.main()
