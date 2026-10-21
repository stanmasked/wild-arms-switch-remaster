#!/usr/bin/env python3
"""Synthetic failure fixtures for Burst guest oracle; NOT emulator evidence."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_arm_burst import (
    audit_burst,NAMES,ZR_HINT,FOE_0_HEALTH,
    ONE_ROUND_LAST,ONE_ROUND_FIRST_EMPTY,
)
from audit_nexium_arm_guest import ARM_FULL_BAR,GOLD,DARK
from test_audit_nexium_arm_cold_boot import cold_fixture
from test_audit_nexium_arm_guest import put


def fixture_burst(root):
    root=Path(root)
    main,cold,*_=cold_fixture(root)
    burst=root/"burst"
    burst.mkdir()
    initial=main/"03_arm_full.png"
    restarted=cold/"10_arm_restart_full.png"
    for path in (initial,restarted):
        with Image.open(path) as old:
            frame=old.convert("RGB")
        put(frame,ZR_HINT,GOLD)
        frame.save(path)
    fired=burst/(NAMES[0]+".png")
    shutil.copyfile(restarted,fired)
    with Image.open(fired) as old:
        frame=old.convert("RGB")
    put(frame,ONE_ROUND_LAST,GOLD)
    put(frame,ONE_ROUND_FIRST_EMPTY,DARK)
    put(frame,ARM_FULL_BAR,DARK)
    put(frame,FOE_0_HEALTH,DARK)
    frame.save(fired)
    shutil.copyfile(fired,burst/(NAMES[1]+".png"))
    return main,cold,burst,root/"burst-audit.json"


class BurstGuestAuditContractTests(unittest.TestCase):
    def test_synthetic_positive_contract_not_real_guest(self):
        with tempfile.TemporaryDirectory() as temp:
            result=audit_burst(*fixture_burst(temp))
            self.assertTrue(result["all_checks_passed"],result["checks"])
            self.assertEqual(len(result["checks"]),7)

    def test_one_bullet_empty_boundary_required(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture_burst(temp)
            path=args[2]/(NAMES[0]+".png")
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,ONE_ROUND_FIRST_EMPTY,GOLD)
            frame.save(path)
            result=audit_burst(*args)
            self.assertFalse(result["checks"]["burst_spent_exactly_two_bullets"])

    def test_zr_held_second_shot_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture_burst(temp)
            path=args[2]/(NAMES[1]+".png")
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,ONE_ROUND_LAST,DARK)
            frame.save(path)
            result=audit_burst(*args)
            self.assertFalse(result["checks"]["held_zr_does_not_refire_or_change_ui"])

    def test_burst_enemy_must_be_defeated(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture_burst(temp)
            path=args[2]/(NAMES[0]+".png")
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,FOE_0_HEALTH,GOLD)
            frame.save(path)
            result=audit_burst(*args)
            self.assertFalse(result["checks"]["burst_one_turn_defeats_initial_14_hp_foe"])

    def test_missing_burst_screen_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture_burst(temp)
            (args[2]/(NAMES[0]+".png")).unlink()
            with self.assertRaises(ValueError):
                audit_burst(*args)


if __name__=="__main__":
    unittest.main()
