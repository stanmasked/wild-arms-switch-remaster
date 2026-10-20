#!/usr/bin/env python3
"""Synthetic adversarial fixture suite for 11th NeXium CRC-recovery auditor."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import screen_point
from audit_nexium_battle_recovery import audit_recovery
from test_audit_nexium_battle_persistence import (
    setup, image, save_fake_journal,
)


def fixture(folder):
    shots, _, a, b, _ = setup(folder)
    directory = Path(folder) / "recovery"
    directory.mkdir()
    image("03_reboot_zl_one").save(
        directory / "00_corrupt_reboot_zl_one.png")
    image("05_reboot_after_second_retreat").save(
        directory / "01_after_repaired_retreat.png")
    broken = Path(folder) / "corrupt-newest.b"
    damaged = bytearray(b.read_bytes())
    damaged[48] ^= 0x80
    broken.write_bytes(damaged)
    repaired_a = Path(folder) / "repaired.a"
    repaired_b = Path(folder) / "repaired.b"
    repaired_a.write_bytes(a.read_bytes())
    repaired_b.write_bytes(b.read_bytes())
    return (directory, shots / "00_first_field.png", a, b,
            broken, repaired_a, repaired_b, Path(folder) / "recovery.json")


class CorruptBattleJournalRecoveryTests(unittest.TestCase):
    def test_positive_real_guest_shape_and_repaired_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_recovery(*fixture(tmp))
            self.assertTrue(report["all_checks_passed"], report["checks"])
            self.assertEqual(len(report["checks"]), 6)

    def test_corruption_must_be_exact_single_outer_checksum_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            damaged = bytearray(args[4].read_bytes())
            damaged[20] ^= 1
            args[4].write_bytes(damaged)
            with self.assertRaises(ValueError):
                audit_recovery(*args)

    def test_missing_image_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            (args[0] / "00_corrupt_reboot_zl_one.png").unlink()
            with self.assertRaises(ValueError):
                audit_recovery(*args)

    def test_extra_image_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            image("00_first_field").save(args[0] / "extra.png")
            with self.assertRaises(ValueError):
                audit_recovery(*args)

    def test_forged_repaired_record_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            save_fake_journal(args[6], 3, 3)
            report = audit_recovery(*args)
            self.assertFalse(report["checks"]["repair_committed_B_as_second_generation_not_third"])
            self.assertFalse(report["checks"]["exact_A_unchanged_and_B_byte_equivalent_after_repair"])

    def test_latest_corrupt_B_not_accepted_as_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            args[4].write_bytes(args[3].read_bytes())
            with self.assertRaises(ValueError):
                audit_recovery(*args)

    def test_missing_reloaded_old_counter_glyph_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            image("00_first_field").save(args[0]/"00_corrupt_reboot_zl_one.png")
            report = audit_recovery(*args)
            self.assertFalse(report["checks"]["eleventh_guest_restores_older_retreat_count_into_ZL"])

    def test_changed_returned_field_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            name = args[0]/"01_after_repaired_retreat.png"
            with Image.open(name) as img:
                modified=img.convert("RGB")
            modified.putpixel(screen_point(620,380),(0,255,12))
            modified.save(name)
            report = audit_recovery(*args)
            self.assertFalse(report["checks"]["eleventh_guest_B_exit_preserves_exact_field_pixels"])

    def test_corrupted_recovered_A_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            raw=bytearray(args[5].read_bytes())
            raw[48]^=0x80
            args[5].write_bytes(raw)
            with self.assertRaises(ValueError):
                audit_recovery(*args)


if __name__ == "__main__":
    unittest.main()
