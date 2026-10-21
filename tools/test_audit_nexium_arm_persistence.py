#!/usr/bin/env python3
"""Synthetic oracle tests for Stage405; never real NeXium evidence."""
import json
import tempfile
import unittest
import zlib
import struct
from pathlib import Path

from PIL import Image

from audit_nexium_arm_persistence import (
    audit_persistence, RETREATS_ONE,
)
from audit_nexium_arm_victory import (
    EXP_START, EXP_8_MIDDLE, GELLA_1, GELLA_2, WINS_ONE, GREEN, GOLD,
)
from audit_nexium_arm_guest import DARK
from audit_nexium_checkpoints import SCREEN_SIZE, screen_point
from test_audit_nexium_battle_two_victories import journal


def put(image, point, color):
    image.putpixel(screen_point(*point), color)


def fixture(root):
    root = Path(root)
    shots = root / "persistence"
    shots.mkdir()
    shot = shots / "23_victory_coldboot_reopen.png"
    image = Image.new("RGB", SCREEN_SIZE, DARK)
    for point in (EXP_START, EXP_8_MIDDLE, GELLA_1, GELLA_2):
        put(image, point, GREEN)
    put(image, WINS_ONE, GOLD)
    put(image, RETREATS_ONE, GOLD)
    image.save(shot)

    arm_root = root / "arm-root"
    directory = arm_root / "sdmc" / "switch" / "wild_arms_field"
    directory.mkdir(parents=True)
    journal(directory / "arm-training-progress.a", 1, 1, 1, 0, 8, 12)
    journal(directory / "arm-training-progress.b", 2, 3, 1, 1, 8, 12)

    processes = root / "persistence-process.json"
    processes.write_text(json.dumps({
        "victoryrestart_pid": 1005,
        "victoryrestart_wait_status": 143,
        "victoryrestart_force_killed": False,
        "victoryrestart_wait_completed": True,
    }), encoding="utf-8")
    victory_process = root / "victory-process.json"
    victory_process.write_text(json.dumps({
        "victory_pid": 1004,
        "victory_wait_status": 143,
        "victory_force_killed": False,
        "victory_wait_completed": True,
    }), encoding="utf-8")
    return shot, processes, victory_process, arm_root, root / "audit.json"


class ArmPersistenceAuditorTests(unittest.TestCase):
    def test_positive_fixture_proves_only_the_oracle_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            result = audit_persistence(*args)
            self.assertTrue(result["all_checks_passed"], result["checks"])
            self.assertEqual(len(result["checks"]), 6)
            self.assertEqual(result["journal"]["older"]["experience"], 8)
            self.assertEqual(result["journal"]["latest"]["retreats"], 1)

    def test_reward_pixels_must_survive_cold_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            with Image.open(args[0]) as src:
                image = src.convert("RGB")
            put(image, GELLA_2, DARK)
            image.save(args[0])
            result = audit_persistence(*args)
            self.assertFalse(result["checks"][
                "real_cold_boot_frame_shows_exact_persisted_exp_and_gella"])

    def test_retreat_history_must_survive_cold_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            with Image.open(args[0]) as src:
                image = src.convert("RGB")
            put(image, RETREATS_ONE, DARK)
            image.save(args[0])
            result = audit_persistence(*args)
            self.assertFalse(result["checks"][
                "real_cold_boot_frame_shows_persisted_retreat_history"])

    def test_latest_journal_must_preserve_exact_reward_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            directory = args[3] / "sdmc/switch/wild_arms_field"
            journal(directory / "arm-training-progress.b", 2, 3, 1, 1, 8, 11)
            result = audit_persistence(*args)
            self.assertFalse(result["checks"][
                "latest_slot_preserves_reward_after_retreat"])

    def test_regular_battle_or_field_save_namespace_is_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            directory = args[3] / "sdmc/switch/wild_arms_field"
            (directory / "battle-progress.a").write_bytes(b"must-not-exist")
            result = audit_persistence(*args)
            self.assertFalse(result["checks"][
                "only_two_arm_progress_slots_exist_in_dedicated_namespace"])

    def test_process_ids_must_be_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = list(fixture(tmp))
            state = json.loads(args[1].read_text(encoding="utf-8"))
            state["victoryrestart_pid"] = 1004
            args[1].write_text(json.dumps(state), encoding="utf-8")
            result = audit_persistence(*args)
            self.assertFalse(result["checks"][
                "fifth_guest_is_a_distinct_terminated_ne_xium_process"])

    def test_corrupt_journal_is_rejected_before_reporting_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture(tmp)
            path = args[3] / "sdmc/switch/wild_arms_field/arm-training-progress.b"
            raw = bytearray(path.read_bytes())
            raw[36] ^= 0x80
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                audit_persistence(*args)


if __name__ == "__main__":
    unittest.main()
