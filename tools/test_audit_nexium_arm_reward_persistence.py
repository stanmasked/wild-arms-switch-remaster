import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image

from audit_nexium_checkpoints import screen_point
from audit_nexium_arm_guest import MAP_STATUS
from audit_nexium_arm_reward_persistence import audit_reward_persistence

SCREEN = (1600, 900)


def record(generation=1, exp=8, gella=12):
    data = bytearray(32)
    data[:4] = b"WAER"
    data[4] = 1
    struct.pack_into("<QII", data, 8, generation, exp, gella)
    struct.pack_into("<I", data, 28, zlib.crc32(data[:28]))
    return bytes(data)


def paint_native(image, x, y, color):
    image.putpixel(screen_point(x, y), color)


class RewardPersistenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.shots = self.root / "screens"
        self.shots.mkdir()
        self.data_root = self.root / "nexium-data"
        self.game_dir = self.data_root / "sdmc" / "switch" / "wild_arms_field"
        self.game_dir.mkdir(parents=True)
        self.first = self.root / "first.a"
        self.after = self.root / "after.a"
        self.processes = self.root / "processes.json"
        self.report = self.root / "report.json"
        self.first.write_bytes(record())
        self.after.write_bytes(record())
        (self.game_dir / "arm-rewards.a").write_bytes(record())
        self._write_processes()
        self._write_screenshots()

    def tearDown(self):
        self.temp.cleanup()

    def _write_processes(self, first_pid=101, second_pid=202,
                         first_root=None, second_root=None):
        root = str(self.data_root.resolve())
        payload = {
            "first_pid": first_pid,
            "second_pid": second_pid,
            "first_wait_completed": True,
            "second_wait_completed": True,
            "first_wait_status": 143,
            "second_wait_status": 143,
            "first_root": root if first_root is None else first_root,
            "second_root": root if second_root is None else second_root,
        }
        self.processes.write_text(json.dumps(payload), encoding="utf-8")

    def _write_screenshots(self, balance_pixels=True):
        field = Image.new("RGB", SCREEN, (12, 19, 31))
        paint_native(field, 0, 5, MAP_STATUS)
        field.save(self.shots / "00_coldboot_field.png")
        balance = Image.new("RGB", SCREEN, (28, 40, 57))
        if balance_pixels:
            for x, y in ((72, 667), (124, 667), (163, 667), (254, 667)):
                paint_native(balance, x, y, MAP_STATUS)
            # Column one in the first digit of 12 is intentionally blank.
        balance.save(self.shots / "01_coldboot_reward_balance.png")

    def _audit(self):
        return audit_reward_persistence(
            self.shots, self.first, self.after, self.processes,
            self.data_root, self.report)

    def test_real_two_process_cold_boot_fixture_passes(self):
        result = self._audit()
        self.assertTrue(result["all_checks_passed"], result["checks"])
        self.assertTrue(self.report.is_file())

    def test_same_process_cannot_claim_cold_boot(self):
        self._write_processes(first_pid=101, second_pid=101)
        self.assertFalse(self._audit()["checks"][
            "two_distinct_ne_xium_processes_completed"])

    def test_wrong_balance_glyph_is_rejected(self):
        self._write_screenshots(balance_pixels=False)
        self.assertFalse(self._audit()["checks"][
            "cold_boot_arm_screen_shows_restored_8_exp_12_gella"])

    def test_rewritten_journal_is_rejected(self):
        self.after.write_bytes(record(generation=2, exp=16, gella=24))
        self.assertFalse(self._audit()["checks"][
            "cold_boot_read_preserved_exact_committed_journal_bytes"])

    def test_foreign_field_or_battle_save_slot_is_rejected(self):
        (self.game_dir / "field-save.a").write_bytes(b"unexpected")
        self.assertFalse(self._audit()["checks"][
            "field_and_regular_battle_save_slots_are_untouched"])

    def test_bad_crc_is_rejected(self):
        bad = bytearray(record())
        bad[16] ^= 1
        self.first.write_bytes(bad)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self._audit()

    def test_mismatched_sdmc_root_is_rejected(self):
        self._write_processes(second_root=str(self.root / "other-root"))
        self.assertFalse(self._audit()["checks"][
            "both_processes_used_the_same_isolated_sdmc_root"])


if __name__ == "__main__":
    unittest.main()
