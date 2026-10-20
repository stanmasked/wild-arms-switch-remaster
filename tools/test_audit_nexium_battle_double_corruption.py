#!/usr/bin/env python3
"""Stage369 adversarial synthetic fixtures; do not mistake these for guest proof."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import screen_point
from audit_nexium_battle_double_corruption import audit_both_corrupt
from test_audit_nexium_battle_alternating_faults import (
    make_case as stage368_fixture, paint_digit, damage,
)
from test_audit_nexium_battle_two_victories import picture
from audit_nexium_battle_alternating_faults import GOLD, GREEN, PANEL


def make_fixture(root):
    root = Path(root)
    before = stage368_fixture(root)
    shots = root / "stage369"
    shots.mkdir()
    valid_a = before[11]
    valid_b = before[12]
    corrupt_a = root / "stage369-damaged-A.a"
    corrupt_b = root / "stage369-damaged-B.b"
    damage(valid_a, corrupt_a)
    damage(valid_b, corrupt_b)
    new = root / "stage369-pids.txt"
    new.write_text("twentythird 1010\ntwentyfourth 1011\n", encoding="ascii")
    keys = root / "stage369-keys.txt"
    expected = [("twentythird", "x"), ("twentythird", "e"),
                ("twentythird", "x"), ("twentyfourth", "x"),
                ("twentyfourth", "e"), ("twentyfourth", "x")]
    keys.write_text("".join(f"{who} 2026-10-20T18:00:00Z {key}\n"
                            for who, key in expected), encoding="ascii")
    # Synthetic zero ZL frame (no emulator needed for this unit test).
    with Image.open(before[0] / "03_twentyfirst_reload_four.png") as f:
        zero = f.convert("RGB")
    for x, y, color in ((776, 650, GOLD), (1013, 623, GREEN),
                        (1078, 623, GREEN)):
        paint_digit(zero, x, y, 0, color)
    paint_digit(zero, 789, 677, 0, (246, 247, 252))
    # Masks for non-digit pixels are incidental to synthetic tests; PNG
    # equality and critical digit checks are strict in the actual audit.
    volatile = zero.copy()
    paint_digit(volatile, 789, 677, 1, (246, 247, 252))
    names = ("00_twentythird_zero_after_corruption",
             "01_twentythird_after_retreat",
             "02_twentythird_volatile_retreat",
             "03_twentyfourth_zero_after_reboot",
             "04_twentyfourth_after_retreat",
             "05_twentyfourth_volatile_retreat")
    for name, frame in zip(names, (zero, picture("07_third_retreat"), volatile,
                                    zero, picture("07_third_retreat"), volatile)):
        frame.save(shots / (name + ".png"))
    after23_a = root / "after23.a"
    after23_b = root / "after23.b"
    after24_a = root / "after24.a"
    after24_b = root / "after24.b"
    for source, dest in ((corrupt_a, after23_a), (corrupt_b, after23_b),
                         (corrupt_a, after24_a), (corrupt_b, after24_b)):
        shutil.copyfile(source, dest)
    return (
        shots, before[1], valid_a, valid_b, corrupt_a, corrupt_b,
        after23_a, after23_b, after24_a, after24_b,
        before[16], new, keys, root / "stage369-report.json",
    )


class BothCorruptTests(unittest.TestCase):
    def test_valid_both_crc_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = audit_both_corrupt(*make_fixture(d))
            self.assertTrue(r["all_checks_passed"], r["checks"])
            self.assertEqual(len(r["checks"]), 12)

    def test_missing_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            (a[0] / "03_twentyfourth_zero_after_reboot.png").unlink()
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_extra_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            picture("01_first_victory").save(a[0] / "sneaky.png")
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_only_one_slot_corrupted_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            shutil.copyfile(a[3], a[5])
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_fault_changed_payload_instead_of_crc_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            raw = bytearray(a[4].read_bytes())
            raw[18] ^= 1
            a[4].write_bytes(raw)
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_first_boot_falsely_displays_old_rewards(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            with Image.open(a[0] / "00_twentythird_zero_after_corruption.png") as f:
                v = f.convert("RGB")
            paint_digit(v, 1013, 623, 3, GREEN)
            v.save(a[0] / "00_twentythird_zero_after_corruption.png")
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentythird_boot_did_not_show_unverifiable_stored_rewards"])

    def test_reboot_falsely_recovers_nonexistent_wins(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            picture("05_second_rewards").save(a[0] / "03_twentyfourth_zero_after_reboot.png")
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentyfourth_guest_reboots_again_with_zero_rewards"])

    def test_first_retreat_overwrites_corrupted_A(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            shutil.copyfile(a[2], a[6])
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentythird_failed_save_did_not_rewrite_either_corrupt_slot"])

    def test_first_retreat_overwrites_corrupted_B(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            shutil.copyfile(a[3], a[7])
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentythird_failed_save_did_not_rewrite_either_corrupt_slot"])

    def test_second_retreat_overwrites_corrupted_A(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            shutil.copyfile(a[2], a[8])
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentyfourth_failed_save_kept_both_corrupt_slots_unchanged"])

    def test_second_retreat_overwrites_corrupted_B(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            shutil.copyfile(a[3], a[9])
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentyfourth_failed_save_kept_both_corrupt_slots_unchanged"])

    def test_volatile_retreat_does_not_reset_in_memory(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            shutil.copyfile(a[0] / "00_twentythird_zero_after_corruption.png",
                            a[0] / "02_twentythird_volatile_retreat.png")
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentythird_retreat_only_updates_volatile_in_memory_history"])

    def test_volatile_retreat_must_not_award_exp(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            with Image.open(a[0] / "05_twentyfourth_volatile_retreat.png") as f:
                im = f.convert("RGB")
            paint_digit(im, 1013, 623, 8, GREEN)
            im.save(a[0] / "05_twentyfourth_volatile_retreat.png")
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["no_earnings_or_fabricated_victory_after_double_CRC_failure"])

    def test_duplicate_new_PID_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            a[11].write_text("twentythird 1010\ntwentyfourth 1010\n")
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_duplicate_prior_PID_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            a[11].write_text("twentythird 1008\ntwentyfourth 1011\n")
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_attack_during_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            a[12].write_text(a[12].read_text().replace("Z e\n", "Z c\n", 1))
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_wrong_original_generation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            from test_audit_nexium_battle_two_victories import journal
            journal(a[2], 3, 1, 2, 1, 16, 24)
            with self.assertRaises(ValueError):
                audit_both_corrupt(*a)

    def test_second_return_field_modified(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_fixture(d)
            fn = a[0] / "04_twentyfourth_after_retreat.png"
            with Image.open(fn) as f:
                image = f.convert("RGB")
            image.putpixel(screen_point(600, 350), (17, 184, 99))
            image.save(fn)
            r = audit_both_corrupt(*a)
            self.assertFalse(r["checks"]["twentyfourth_retreat_returns_original_field"])


if __name__ == "__main__":
    unittest.main()
