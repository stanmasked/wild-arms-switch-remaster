#!/usr/bin/env python3
"""Host-synthetic fixtures ONLY; real NeXium verification requires CI guest frames."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image, ImageDraw
from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, screen_point
from audit_nexium_battle_two_victories import (
    NAMES, audit_two_victories, GREEN, GOLD, PANEL, DARK,
)
FIELD = (14, 20, 34)
RED = (201, 67, 76)


def journal(path, generation, outcome, wins, retreats, exp, gella):
    inner = bytearray(36)
    inner[:4] = b"WABR"
    inner[4], inner[5] = 1, outcome
    for offset, value in ((8, wins), (16, retreats), (20, exp), (24, gella)):
        struct.pack_into("<I", inner, offset, value)
    struct.pack_into("<I", inner, 32, zlib.crc32(inner[:32]))
    raw = bytearray(52)
    raw[:4] = b"WABJ"
    struct.pack_into("<Q", raw, 4, generation)
    raw[12:48] = inner
    struct.pack_into("<I", raw, 48, zlib.crc32(raw[:48]))
    Path(path).write_bytes(raw)


def picture(name):
    native = Image.new("RGB", (1280, 720), DARK if "victory" in name else FIELD)
    d = ImageDraw.Draw(native)
    if "victory" in name:
        d.rectangle((321, 295, 950, 397), outline=GREEN, width=2)
        d.rectangle((322, 296, 326, 300), fill=GREEN)
    else:
        d.rectangle((0, 0, 1279, 9), fill=GREEN)
        d.rectangle((340, 230, 369, 250), fill=RED)
        if name in ("02_first_rewards", "03_second_reload",
                    "05_second_rewards", "06_third_reload"):
            d.rectangle((690, 612, 1239, 707), fill=PANEL)
            d.rectangle((690, 612, 1239, 615), fill=GOLD)
            if name in ("02_first_rewards", "03_second_reload"):
                d.rectangle((779, 654, 781, 658), fill=GOLD)
                for x, y in ((1015, 629), (1080, 625), (1091, 635)):
                    d.rectangle((x, y, x+2, y+1), fill=GREEN)
            else:
                d.rectangle((782, 654, 783, 658), fill=GOLD)
                for x, y in ((1017, 629), (1027, 629),
                             (1093, 623), (1105, 631)):
                    d.rectangle((x, y, x+2, y+1), fill=GREEN)
    screen = Image.new("RGB", SCREEN_SIZE)
    screen.paste(native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST),
                 (VIEW_X, 0))
    return screen


def fixture(folder):
    root = Path(folder)
    shots = root / "shots"
    shots.mkdir()
    for name in NAMES:
        picture(name).save(shots / (name + ".png"))
    paths = tuple(root / name for name in
                  ("first.a", "second.a", "second.b", "final.a", "final.b"))
    journal(paths[0], 1, 1, 1, 0, 8, 12)
    journal(paths[1], 1, 1, 1, 0, 8, 12)
    journal(paths[2], 2, 1, 2, 0, 16, 24)
    journal(paths[3], 3, 3, 2, 1, 16, 24)
    journal(paths[4], 2, 1, 2, 0, 16, 24)
    pids = root / "pids.txt"
    pids.write_text("fourteenth 1001\nfifteenth 1002\nsixteenth 1003\n")
    return (shots, *paths, pids, root / "result.json")


class TwoVictoryOracleTests(unittest.TestCase):
    def test_valid_three_process_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_two_victories(*fixture(tmp))
            self.assertTrue(result["all_checks_passed"], result["checks"])
            self.assertEqual(len(result["checks"]), 14)
            self.assertEqual(len(result["sha256"]), 14)

    def test_missing_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            (args[0] / "04_second_victory.png").unlink()
            with self.assertRaises(ValueError):
                audit_two_victories(*args)

    def test_extra_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            picture("01_first_victory").save(args[0] / "extra.png")
            with self.assertRaises(ValueError):
                audit_two_victories(*args)

    def test_duplicate_process_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            args[-2].write_text("fourteenth 1001\nfifteenth 1001\nsixteenth 1003\n")
            with self.assertRaises(ValueError):
                audit_two_victories(*args)

    def test_corrupted_inner_crc_with_valid_outer_crc_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            data = bytearray(args[3].read_bytes())
            data[44] ^= 1
            struct.pack_into("<I", data, 48, zlib.crc32(data[:48]))
            args[3].write_bytes(data)
            with self.assertRaises(ValueError):
                audit_two_victories(*args)

    def test_false_second_victory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            picture("00_first_manual").save(args[0] / "04_second_victory.png")
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["seven_second_guest_A_attacks_reached_actual_victory"])

    def test_forged_second_rewards_pixel_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            picture("02_first_rewards").save(args[0] / "05_second_rewards.png")
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["second_guest_renders_two_wins_sixteen_EXP_twentyfour_Gella"])

    def test_third_guest_forged_reload_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            picture("02_first_rewards").save(args[0] / "06_third_reload.png")
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["third_fresh_guest_restores_two_wins_before_combat"])

    def test_duplicate_awards_in_second_generation_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            journal(args[3], 2, 1, 2, 0, 24, 36)
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["second_victory_committed_gen2_sixteen_EXP_twentyfour_Gella"])

    def test_first_committed_generation_mutation_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            journal(args[2], 1, 1, 1, 0, 9, 12)
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["first_generation_slot_A_unchanged_after_second_win"])

    def test_second_generation_mutation_after_third_guest_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            journal(args[5], 2, 1, 2, 0, 16, 25)
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["second_generation_slot_B_unchanged_after_third_guest"])

    def test_retreat_does_not_credit_more_EXP_Gella(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            journal(args[4], 3, 3, 2, 1, 24, 36)
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["third_guest_retreat_commits_gen3_without_extra_rewards"])

    def test_changed_return_field_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            path = args[0] / "07_third_retreat.png"
            with Image.open(path) as image:
                rgb = image.convert("RGB")
            rgb.putpixel(screen_point(600, 350), (34, 200, 1))
            rgb.save(path)
            result = audit_two_victories(*args)
            self.assertFalse(result["checks"]["third_guest_retreat_restores_original_field"])


if __name__ == "__main__":
    unittest.main()
