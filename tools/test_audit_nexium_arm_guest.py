#!/usr/bin/env python3
"""Synthetic, explicitly non-guest negative fixtures for Stage390's auditor."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_checkpoints import SCREEN_SIZE, screen_point
from audit_nexium_arm_guest import (
    SCREENSHOTS, ARM_BORDER, ARM_FULL_BAR, ARM_PARTIAL_BAR, ARM_PAST_PARTIAL,
    GOLD, BLUE, RED, DARK, MAP_STATUS, audit_arm_guests,
)
from test_audit_nexium_battle_two_victories import journal


def put(image, point, rgb):
    image.putpixel(screen_point(*point), rgb)


def fixture(root):
    root=Path(root)
    shots=root/"screens"
    shots.mkdir()
    baseline=root/"baseline"
    arm=root/"arm"
    (baseline/"sdmc/switch/wild_arms_field").mkdir(parents=True)
    (arm/"sdmc/switch/wild_arms_field").mkdir(parents=True)
    journal(baseline/"sdmc/switch/wild_arms_field/battle-progress.a",
            1,3,0,1,0,0)
    process=root/"processes.json"
    process.write_text(json.dumps({
        "baseline_pid":1001,"arm_pid":1002,
        "baseline_wait_completed":True,"arm_wait_completed":True,
        "baseline_wait_status":143,"arm_wait_status":143}))

    field=Image.new("RGB",SCREEN_SIZE,DARK)
    put(field,(0,5),MAP_STATUS)
    normal=field.copy()
    put(normal,(70,220),BLUE)
    put(normal,(670,165),GOLD)
    full=normal.copy()
    put(full,ARM_BORDER,GOLD)
    put(full,ARM_FULL_BAR,GOLD)
    put(full,ARM_PARTIAL_BAR,GOLD)
    put(full,ARM_PAST_PARTIAL,GOLD)
    fired=full.copy()
    put(fired,ARM_FULL_BAR,DARK)
    put(fired,ARM_PARTIAL_BAR,GOLD)
    put(fired,ARM_PAST_PARTIAL,DARK)
    put(fired,(692+100,249),RED)
    put(fired,(692+230,249),DARK)
    reloaded=fired.copy()
    put(reloaded,ARM_FULL_BAR,GOLD)

    images=(field,normal,field.copy(),full,fired,fired.copy(),
            reloaded,field.copy())
    for name,img in zip(SCREENSHOTS,images):
        img.save(shots/(name+".png"))
    return shots,baseline,arm,process,root/"audit.json"


class StrictArmGuestAuditorTests(unittest.TestCase):
    def test_synthetic_positive_only_proves_auditor_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            a=fixture(temp)
            result=audit_arm_guests(*a)
            self.assertTrue(result["all_checks_passed"],result["checks"])
            self.assertEqual(len(result["checks"]),10)
            self.assertEqual(len(result["sha256"]),8)

    def test_fake_repeat_shot_is_rejected_by_pixel_parity(self):
        with tempfile.TemporaryDirectory() as temp:
            a=fixture(temp)
            path=a[0]/"05_arm_fire_held.png"
            with Image.open(path) as original:
                image=original.convert("RGB")
            put(image,ARM_PARTIAL_BAR,DARK)
            image.save(path)
            result=audit_arm_guests(*a)
            self.assertFalse(result["all_checks_passed"])
            self.assertFalse(result["checks"]["held_x_did_not_double_fire"])

    def test_panel_only_late_change_is_detected_outside_game_roi(self):
        # If only the HUD flickers/updates on a held X, central game
        # pixels cannot reveal it. Entire displayed ammo panel must match.
        with tempfile.TemporaryDirectory() as temp:
            args = fixture(temp)
            path = args[0] / "05_arm_fire_held.png"
            with Image.open(path) as original:
                held = original.convert("RGB")
            put(held, (944 + 90, 622 + 25), RED)
            held.save(path)
            result = audit_arm_guests(*args)
            self.assertFalse(result["checks"]["held_x_did_not_double_fire"])

    def test_held_shot_fully_preserves_bar_not_only_enemy_hp(self):
        with tempfile.TemporaryDirectory() as temp:
            args = fixture(temp)
            path = args[0] / "05_arm_fire_held.png"
            with Image.open(path) as original:
                held = original.convert("RGB")
            put(held, ARM_FULL_BAR, GOLD)
            held.save(path)
            result = audit_arm_guests(*args)
            self.assertFalse(result["checks"]["held_x_did_not_double_fire"])

    def test_any_arm_journal_created_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            a=fixture(temp)
            journal(a[2]/"sdmc/switch/wild_arms_field/battle-progress.a",
                    1,3,0,1,0,0)
            result=audit_arm_guests(*a)
            self.assertFalse(result["checks"]["arm_training_never_created_wabj_slots"])

    def test_corrupted_baseline_wabj_is_not_valid_positive_control(self):
        with tempfile.TemporaryDirectory() as temp:
            a=fixture(temp)
            path=a[1]/"sdmc/switch/wild_arms_field/battle-progress.a"
            damaged=bytearray(path.read_bytes())
            damaged[48]^=0xFF
            path.write_bytes(damaged)
            result=audit_arm_guests(*a)
            self.assertFalse(
                result["checks"]["normal_b_close_wrote_valid_single_retreat_journal"])

    def test_identical_roots_and_missing_screen_fail_strict_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            a=fixture(temp)
            with self.assertRaises(ValueError):
                audit_arm_guests(a[0],a[1],a[1],a[3],a[4])
            (a[0]/"04_arm_fired.png").unlink()
            with self.assertRaises(ValueError):
                audit_arm_guests(*a)

    def test_unexpected_guest_exit_is_rejected_even_with_valid_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            args = fixture(temp)
            evidence = json.loads(args[3].read_text())
            evidence["arm_wait_status"] = 124  # Emulator timeout, not intentional stop.
            args[3].write_text(json.dumps(evidence))
            result = audit_arm_guests(*args)
            self.assertFalse(result["checks"]["two_independent_guest_processes"])

    def test_process_identity_is_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            a=fixture(temp)
            same={"baseline_pid":1001,"arm_pid":1001,
                  "baseline_wait_completed":True,"arm_wait_completed":True,
                  "baseline_wait_status":143,"arm_wait_status":143}
            a[3].write_text(json.dumps(same))
            result=audit_arm_guests(*a)
            self.assertFalse(result["checks"]["two_independent_guest_processes"])


if __name__=="__main__":
    unittest.main()
