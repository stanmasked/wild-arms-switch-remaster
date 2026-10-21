#!/usr/bin/env python3
"""Stage396 host-only synthetic checks: NEVER counted as actual guest data."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_arm_cold_boot import NAMES, audit_arm_cold_boot
from test_audit_nexium_arm_guest import fixture, put
from audit_nexium_arm_guest import ARM_FULL_BAR, DARK, RED


def cold_fixture(root):
    root=Path(root)
    shots,baseline,arm,processes,_=fixture(root)
    cold=root/"coldboot"
    cold.mkdir()
    for new,old in zip(NAMES,("00_baseline_field",
                               "03_arm_full","00_baseline_field")):
        shutil.copyfile(shots/(old+".png"),cold/(new+".png"))
    # The old synthetic HUD-only fixture does not paint the untouched
    # foe HP bar. Both genuine guest opening screens MUST expose it,
    # so add that exact invariant to both reference and third images.
    for name in (shots/"03_arm_full.png",cold/"09_arm_restart_full.png"):
        with Image.open(name) as original:
            unspent=original.convert("RGB")
        put(unspent,(692+230,249),RED)
        unspent.save(name)
    third=root/"third-process.json"
    third.write_text(json.dumps({
        "armrestart_pid":1003,"armrestart_wait_status":143,
        "armrestart_force_killed":False,"armrestart_wait_completed":True}))
    return shots,cold,processes,third,arm,root/"cold-audit.json"


class ArmColdBootOracleTests(unittest.TestCase):
    def test_positive_synthetic_contract_not_guest_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            r=audit_arm_cold_boot(*args)
            self.assertTrue(r["all_checks_passed"],r["checks"])
            self.assertEqual(len(r["checks"]),7)
            self.assertEqual(len(r["sha256"]),3)

    def test_reboot_does_not_keep_spent_ammo(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            path=args[1]/"09_arm_restart_full.png"
            with Image.open(path) as original:
                frame=original.convert("RGB")
            put(frame,ARM_FULL_BAR,DARK)
            frame.save(path)
            result=audit_arm_cold_boot(*args)
            self.assertFalse(result["checks"]["new_zl_r_reset_magazine_three_of_three"])
            self.assertFalse(result["checks"]["cold_boot_matches_initial_unspent_arm_scene"])

    def test_unknown_file_in_same_sdmc_rejects_reboot(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            (args[4]/"sdmc/switch/wild_arms_field"/"field-save.tmp").write_bytes(b"BAD")
            result=audit_arm_cold_boot(*args)
            self.assertFalse(result["checks"]["same_real_sdmc_restart_still_empty"])
            self.assertFalse(result["checks"]["cold_boot_never_creates_battle_or_field_save"])

    def test_process_reuse_is_not_independent_cold_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            evidence=json.loads(args[3].read_text())
            evidence["armrestart_pid"]=1002
            args[3].write_text(json.dumps(evidence))
            result=audit_arm_cold_boot(*args)
            self.assertFalse(result["checks"]["three_distinct_true_nexium_processes"])

    def test_unverified_forced_exit_status_137_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            evidence=json.loads(args[3].read_text())
            evidence["armrestart_wait_status"]=137
            args[3].write_text(json.dumps(evidence))
            result=audit_arm_cold_boot(*args)
            self.assertFalse(result["checks"]["three_distinct_true_nexium_processes"])
            evidence["armrestart_force_killed"]=True
            args[3].write_text(json.dumps(evidence))
            result=audit_arm_cold_boot(*args)
            self.assertTrue(result["checks"]["three_distinct_true_nexium_processes"])

    def test_missing_or_invalid_cold_screen_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            (args[1]/"09_arm_restart_full.png").unlink()
            with self.assertRaises(ValueError):
                audit_arm_cold_boot(*args)
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            (args[1]/"10_arm_restart_return.png").write_bytes(b"not a PNG")
            with self.assertRaises((OSError,ValueError)):
                audit_arm_cold_boot(*args)

    def test_guest_cold_return_must_match_original_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=cold_fixture(tmp)
            p=args[1]/"10_arm_restart_return.png"
            with Image.open(p) as original:
                frame=original.convert("RGB")
            put(frame,(600,410),(255,70,20))
            frame.save(p)
            r=audit_arm_cold_boot(*args)
            self.assertFalse(r["checks"]["third_guest_b_returns_without_side_effect"])


if __name__=="__main__":
    unittest.main()
