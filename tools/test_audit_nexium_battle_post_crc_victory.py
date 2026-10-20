#!/usr/bin/env python3
"""Synthetic adversarial oracle fixtures; not real guest screenshot evidence."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import screen_point
from audit_nexium_battle_post_crc_victory import audit_post_repair, GREEN, GOLD, PANEL
from test_audit_nexium_battle_latest_crc_fallback import make_case
from test_audit_nexium_battle_two_victories import picture, journal


def make_three_win_panel():
    img = picture("05_second_rewards")
    samples = {
        (778, 656): GOLD, (780, 656): GOLD, (782, 656): GOLD,
        (1017, 629): PANEL, (1019, 629): GREEN, (1026, 629): GREEN,
        (1093, 629): GREEN, (1108, 629): GREEN, (1106, 631): PANEL,
    }
    for pos, color in samples.items():
        img.putpixel(screen_point(*pos), color)
    return img


def fixture(root):
    root = Path(root)
    prev = make_case(root)
    shots = root / "eighteenth-nineteenth"
    shots.mkdir()
    names = (
        "00_eighteenth_restored_gen3", "01_eighteenth_third_victory",
        "02_eighteenth_three_win_rewards",
        "03_nineteenth_reload_three_wins",
        "04_nineteenth_after_retreat",
    )
    shutil.copyfile(prev[0] / "00_crc_fallback_rewards.png", shots / (names[0] + ".png"))
    picture("01_first_victory").save(shots / (names[1] + ".png"))
    three = make_three_win_panel()
    for name in names[2:4]:
        three.save(shots / (name + ".png"))
    picture("07_third_retreat").save(shots / (names[4] + ".png"))
    gen3 = root / "third-win-old-gen3.a"
    gen2 = root / "third-win-old-gen2.b"
    third_a = root / "after-18th.a"
    third_b = root / "after-18th.b"
    last_a = root / "after-19th.a"
    last_b = root / "after-19th.b"
    for src, dst in ((prev[6], gen3), (prev[7], gen2), (prev[6], third_a)):
        shutil.copyfile(src, dst)
    journal(third_b, 4, 1, 3, 1, 24, 36)
    journal(last_a, 5, 3, 3, 2, 24, 36)
    shutil.copyfile(third_b, last_b)
    pids = root / "new-pids.txt"
    pids.write_text("eighteenth 1005\nnineteenth 1006\n", encoding="ascii")
    keys = root / "new-keys.txt"
    names = ["x", "e", *(["c"] * 7), "x", "x", "e", "x"]
    keys.write_text("".join("2026-10-20T16:00:00Z " + k + "\n" for k in names),
                    encoding="ascii")
    return (
        shots, prev[1], prev[2], gen3, gen2, third_a, third_b, last_a,
        last_b, prev[8], prev[9], pids, keys, root / "result.json",
    )


class PostRepairVictoryTests(unittest.TestCase):
    def test_valid_repaired_save_then_third_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_post_repair(*fixture(tmp))
            self.assertTrue(result["all_checks_passed"], result["checks"])
            self.assertEqual(len(result["checks"]), 13)

    def test_missing_frame_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            (a[0] / "01_eighteenth_third_victory.png").unlink()
            with self.assertRaises(ValueError):
                audit_post_repair(*a)

    def test_extra_frame_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            picture("00_first_manual").save(a[0] / "fake.png")
            with self.assertRaises(ValueError):
                audit_post_repair(*a)

    def test_wrong_repaired_gen3_counters_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            journal(a[3], 3, 3, 2, 1, 8, 12)
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["stage366_repaired_gen3_A_starts_at_two_wins_16_24"])

    def test_forged_second_wins_before_combat_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            picture("00_first_manual").save(a[0] / "00_eighteenth_restored_gen3.png")
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["eighteenth_fresh_guest_restores_two_wins_and_reward_digits"])

    def test_victory_screenshot_must_be_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            picture("00_first_manual").save(a[0] / "01_eighteenth_third_victory.png")
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["seven_new_distinct_real_A_strikes_reach_third_victory"])

    def test_three_win_panel_tamper_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            picture("05_second_rewards").save(a[0] / "02_eighteenth_three_win_rewards.png")
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["eighteenth_guest_ZL_renders_three_wins_24EXP_36Gella"])

    def test_forged_nineteenth_reload_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            picture("05_second_rewards").save(a[0] / "03_nineteenth_reload_three_wins.png")
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["nineteenth_process_restores_exact_three_win_panel_before_fighting"])

    def test_third_win_duplicate_reward_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            journal(a[6], 4, 1, 3, 1, 32, 48)
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["third_win_writes_generation_four_in_slot_B"])

    def test_modified_A_during_third_win_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            journal(a[5], 3, 3, 2, 1, 24, 36)
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["third_win_does_not_change_repaired_gen3_slot_A"])

    def test_nineteenth_retreat_duplicate_credit_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            journal(a[7], 5, 3, 3, 2, 32, 48)
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["nineteenth_retreat_writes_generation_five_in_A_without_reward"])

    def test_generation_four_B_modified_after_reload_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            journal(a[8], 4, 1, 3, 1, 24, 37)
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["generation_four_B_remains_bit_for_bit_unchanged_after_retreat"])

    def test_corrupt_nested_crc_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            raw = bytearray(a[6].read_bytes())
            raw[20] ^= 4
            a[6].write_bytes(raw)
            with self.assertRaises(ValueError):
                audit_post_repair(*a)

    def test_duplicate_pid_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            a[11].write_text("eighteenth 1005\nnineteenth 1005\n")
            with self.assertRaises(ValueError):
                audit_post_repair(*a)

    def test_seven_attack_edges_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            raw = a[12].read_text()
            a[12].write_text(raw.replace("Z c\n", "Z e\n", 1))
            with self.assertRaises(ValueError):
                audit_post_repair(*a)

    def test_returned_field_pixel_changed_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fixture(tmp)
            path = a[0] / "04_nineteenth_after_retreat.png"
            with Image.open(path) as image:
                img = image.convert("RGB")
            img.putpixel(screen_point(600, 350), (42, 200, 31))
            img.save(path)
            result = audit_post_repair(*a)
            self.assertFalse(result["checks"]["nineteenth_guest_retreat_returns_to_unchanged_field"])


if __name__ == "__main__":
    unittest.main()
