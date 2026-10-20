#!/usr/bin/env python3
"""Synthetic adversarial fixtures, not proof of a real NeXium guest run."""
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import screen_point
from audit_nexium_battle_latest_crc_fallback import audit_fallback
from test_audit_nexium_battle_two_victories import fixture, journal, picture


def make_case(root):
    root = Path(root)
    parent = fixture(root)
    shots, _, _, _, gen3, gen2, old_pids, _ = parent
    recovery = root / "recovery"
    recovery.mkdir()
    shutil.copyfile(shots / "06_third_reload.png",
                    recovery / "00_crc_fallback_rewards.png")
    shutil.copyfile(shots / "07_third_retreat.png",
                    recovery / "01_after_repaired_retreat.png")
    original_a = root / "original-gen3.a"
    old_b = root / "fallback-gen2.b"
    corrupt = root / "corrupted-gen3.a"
    repaired_a = root / "repaired-gen3.a"
    repaired_b = root / "still-gen2.b"
    for src, dst in ((gen3, original_a), (gen2, old_b),
                     (gen3, repaired_a), (gen2, repaired_b)):
        shutil.copyfile(src, dst)
    raw = bytearray(original_a.read_bytes())
    raw[48] ^= 0x80
    corrupt.write_bytes(raw)
    fresh_pid = root / "seventeenth-pid.txt"
    fresh_pid.write_text("seventeenth 1004\n", encoding="ascii")
    return (recovery, shots / "00_first_manual.png",
            shots / "06_third_reload.png", original_a, old_b,
            corrupt, repaired_a, repaired_b, old_pids, fresh_pid,
            root / "fallback-report.json")


class LatestBattleFallbackTests(unittest.TestCase):
    def test_positive_two_win_fallback_and_repair(self):
        with tempfile.TemporaryDirectory() as d:
            r = audit_fallback(*make_case(d))
            self.assertTrue(r["all_checks_passed"], r["checks"])
            self.assertEqual(len(r["checks"]), 9)
            self.assertEqual(len(r["sha256"]), 9)

    def test_missing_guest_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            (a[0] / "00_crc_fallback_rewards.png").unlink()
            with self.assertRaises(ValueError):
                audit_fallback(*a)

    def test_extra_guest_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            picture("00_first_manual").save(a[0] / "extra.png")
            with self.assertRaises(ValueError):
                audit_fallback(*a)

    def test_wrong_fault_byte_rejected_even_if_crc_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            bad = bytearray(a[5].read_bytes())
            bad[47] ^= 1
            a[5].write_bytes(bad)
            with self.assertRaises(ValueError):
                audit_fallback(*a)

    def test_fully_valid_unmodified_newest_a_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            shutil.copyfile(a[3], a[5])
            with self.assertRaises(ValueError):
                audit_fallback(*a)

    def test_wrong_second_win_reward_value_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[4], 2, 1, 2, 0, 24, 36)
            r = audit_fallback(*a)
            self.assertFalse(r["checks"]["older_gen2_B_has_two_wins_zero_retreat_and_16_24"])

    def test_wrong_latest_generation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[3], 4, 3, 2, 1, 16, 24)
            r = audit_fallback(*a)
            self.assertFalse(r["checks"]["original_gen3_A_has_two_wins_one_retreat_and_16_24"])

    def test_unchanged_bad_latest_a_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            # The corrupted A is not a valid replacement for a repaired A.
            shutil.copyfile(a[5], a[6])
            with self.assertRaises(ValueError):
                audit_fallback(*a)

    def test_repaired_a_credits_duplicate_reward_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[6], 3, 3, 2, 1, 24, 36)
            r = audit_fallback(*a)
            self.assertFalse(r["checks"]["damaged_slot_was_repaired_to_gen3_only_after_retreat"])
            self.assertFalse(r["checks"]["no_extra_reward_or_double_credit_after_repaired_retreat"])

    def test_prior_b_mutated_after_repair_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[7], 2, 1, 2, 0, 16, 25)
            r = audit_fallback(*a)
            self.assertFalse(r["checks"]["prior_gen2_B_was_never_modified"])

    def test_forged_restored_panel_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            picture("02_first_rewards").save(a[0] / "00_crc_fallback_rewards.png")
            r = audit_fallback(*a)
            self.assertFalse(r["checks"]["fallback_guest_ZL_restored_previous_wins_EXP_and_Gella"])

    def test_changed_field_after_retreat_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            path = a[0] / "01_after_repaired_retreat.png"
            with Image.open(path) as image:
                frame = image.convert("RGB")
            frame.putpixel(screen_point(600, 350), (33, 212, 1))
            frame.save(path)
            r = audit_fallback(*a)
            self.assertFalse(r["checks"]["seventeenth_guest_returned_exact_original_field"])

    def test_duplicate_pid_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            a[9].write_text("seventeenth 1002\n", encoding="ascii")
            with self.assertRaises(ValueError):
                audit_fallback(*a)

    def test_missing_prior_process_provenance_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            a[8].write_text("fourteenth 1001\nfifteenth 1002\n", encoding="ascii")
            with self.assertRaises(ValueError):
                audit_fallback(*a)


if __name__ == "__main__":
    unittest.main()
