#!/usr/bin/env python3
"""Synthetic Stage400 oracle controls; not real emulator pixels."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_arm_readiness import (
    audit_readiness, STATUS_B, READY_R, NEED_N, GREEN, PANEL,
)
from audit_nexium_arm_guest import GOLD
from test_audit_nexium_arm_burst import fixture_burst
from test_audit_nexium_arm_guest import put


def fixture(root):
    original,cold,burst,_=fixture_burst(root)
    images=(
        (original/"01_baseline_r_battle.png",None),
        (original/"03_arm_full.png","ready"),
        (original/"04_arm_fired.png","ready"),
        (original/"06_arm_reloaded.png","ready"),
        (cold/"10_arm_restart_full.png","ready"),
        (burst/"12_arm_burst_fired.png","need"),
        (burst/"13_arm_burst_held.png","need"),
    )
    for path,kind in images:
        with Image.open(path) as src:
            frame=src.convert("RGB")
        put(frame,STATUS_B,PANEL if kind is None else
            (GREEN if kind=="ready" else GOLD))
        put(frame,READY_R,GREEN if kind=="ready" else PANEL)
        put(frame,NEED_N,GOLD if kind=="need" else PANEL)
        frame.save(path)
    return original,cold,burst,Path(root)/"readiness.json"


class BurstReadinessGuestOracleTests(unittest.TestCase):
    def test_synthetic_happy_path_is_not_ne_xium_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            result=audit_readiness(*args)
            self.assertTrue(result["all_checks_passed"],result["checks"])
            self.assertEqual(len(result["checks"]),7)
            self.assertEqual(len(result["sha256"]),7)

    def test_full_magazine_must_show_green_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            path=args[0]/"03_arm_full.png"
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,STATUS_B,GOLD)
            frame.save(path)
            r=audit_readiness(*args)
            self.assertFalse(r["checks"]["full_three_of_three_burst_ready_green"])

    def test_one_round_must_show_gold_need_two(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            path=args[2]/"12_arm_burst_fired.png"
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,STATUS_B,GREEN)
            frame.save(path)
            r=audit_readiness(*args)
            self.assertFalse(r["checks"]["after_zr_burst_one_of_three_need_two_gold"])

    def test_glyph_ready_vs_need_cannot_be_confused(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            path=args[2]/"12_arm_burst_fired.png"
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,NEED_N,PANEL)
            frame.save(path)
            r=audit_readiness(*args)
            self.assertFalse(r["checks"]["after_zr_burst_one_of_three_need_two_gold"])

    def test_held_zr_status_must_stay_warned(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            path=args[2]/"13_arm_burst_held.png"
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,READY_R,GOLD)
            frame.save(path)
            r=audit_readiness(*args)
            self.assertFalse(r["checks"]["holding_zr_keeps_need_two_gold"])

    def test_normal_r_battle_must_not_acquire_burst_status(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            path=args[0]/"01_baseline_r_battle.png"
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,STATUS_B,GREEN)
            frame.save(path)
            r=audit_readiness(*args)
            self.assertFalse(r["checks"]["ordinary_r_has_no_burst_readiness_overlay"])

    def test_missing_reboot_image_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            args=fixture(temp)
            (args[1]/"10_arm_restart_full.png").unlink()
            with self.assertRaises(ValueError):
                audit_readiness(*args)


if __name__=="__main__":
    unittest.main()
