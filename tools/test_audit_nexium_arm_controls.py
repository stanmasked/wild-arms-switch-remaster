#!/usr/bin/env python3
"""Synthetic negative tests of new ARM hint pixel oracle, NOT guest proof."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_arm_controls import (
    audit_controls,MAIN_SHOTS,REBOOT_SHOT,PROMPT_POSITIONS,RIGHT_BORDER,WHITE,
)
from audit_nexium_arm_guest import GOLD,DARK
from test_audit_nexium_arm_cold_boot import cold_fixture
from test_audit_nexium_arm_guest import put


def control_fixture(root):
    root=Path(root)
    main,cold,_,_,_,_=cold_fixture(root)
    for name in MAIN_SHOTS[1:]:
        path=main/(name+".png")
        with Image.open(path) as original:
            frame=original.convert("RGB")
        for pos in PROMPT_POSITIONS.values():
            put(frame,pos,WHITE)
        put(frame,RIGHT_BORDER,GOLD)
        frame.save(path)
    p=cold/(REBOOT_SHOT+".png")
    with Image.open(p) as original:
        frame=original.convert("RGB")
    for pos in PROMPT_POSITIONS.values():
        put(frame,pos,WHITE)
    put(frame,RIGHT_BORDER,GOLD)
    frame.save(p)
    return main,cold,root/"controls-report.json"


class ArmControlsPixelOracleTests(unittest.TestCase):
    def test_synthetic_complete_hint_oracle_only(self):
        with tempfile.TemporaryDirectory() as temp:
            args=control_fixture(temp)
            r=audit_controls(*args)
            self.assertEqual(len(r["checks"]),5)
            self.assertEqual(len(r["images_sha256"]),5)
            self.assertTrue(r["all_checks_passed"],r["checks"])

    def test_missing_x_hint_after_fire_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            args=control_fixture(temp)
            path=args[0]/"04_arm_fired.png"
            with Image.open(path) as original:
                frame=original.convert("RGB")
            put(frame,PROMPT_POSITIONS["X_FIRE"],DARK)
            frame.save(path)
            r=audit_controls(*args)
            self.assertFalse(r["checks"][
                "arm_spent_ammo_still_shows_fire_reload_controls"])

    def test_missing_reload_prompt_after_coldboot_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            args=control_fixture(temp)
            path=args[1]/(REBOOT_SHOT+".png")
            with Image.open(path) as original:
                frame=original.convert("RGB")
            put(frame,PROMPT_POSITIONS["RELOAD"],DARK)
            frame.save(path)
            r=audit_controls(*args)
            self.assertFalse(r["checks"][
                "third_guest_cold_boot_shows_same_controls"])

    def test_normal_battle_must_not_show_arm_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            args=control_fixture(temp)
            path=args[0]/"01_baseline_r_battle.png"
            with Image.open(path) as original:
                frame=original.convert("RGB")
            put(frame,PROMPT_POSITIONS["X_FIRE"],WHITE)
            frame.save(path)
            r=audit_controls(*args)
            self.assertFalse(r["checks"][
                "ordinary_r_battle_has_no_arm_prompt"])

    def test_hint_cannot_erase_panel_border(self):
        with tempfile.TemporaryDirectory() as temp:
            args=control_fixture(temp)
            path=args[0]/"03_arm_full.png"
            with Image.open(path) as original:
                frame=original.convert("RGB")
            put(frame,RIGHT_BORDER,WHITE)
            frame.save(path)
            r=audit_controls(*args)
            self.assertFalse(r["checks"][
                "arm_full_magazine_shows_x_fire_minus_reload"])

    def test_missing_cold_guest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            args=control_fixture(temp)
            (args[1]/(REBOOT_SHOT+".png")).unlink()
            with self.assertRaises(ValueError):
                audit_controls(*args)


if __name__=="__main__":
    unittest.main()
