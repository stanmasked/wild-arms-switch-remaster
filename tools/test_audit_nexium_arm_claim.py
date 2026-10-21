#!/usr/bin/env python3
"""Synthetic Stage402 preview oracle cases (NOT genuine emulator evidence)."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_arm_claim import (
    audit_claim, CLAIM_GLYPHS, RIGHT_MARGIN, NAMES, GREEN,
)
from audit_nexium_arm_guest import DARK
from test_audit_nexium_arm_victory import fixture_victory
from test_audit_nexium_arm_guest import put


def claim_fixture(root):
    victory,ordinary,*_=fixture_victory(root)
    path=victory/"19_victory_banner.png"
    with Image.open(path) as src:
        bitmap=src.convert("RGB")
    for point in CLAIM_GLYPHS.values():
        put(bitmap,point,GREEN)
    put(bitmap,RIGHT_MARGIN,DARK)
    bitmap.save(path)
    return ordinary,victory,Path(root)/"claim-audit.json"


class RealVictoryClaimAuditorContract(unittest.TestCase):
    def test_synthetic_positive_is_only_oracle_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=audit_claim(*claim_fixture(tmp))
            self.assertTrue(result["all_checks_passed"],result["checks"])
            self.assertEqual(len(result["checks"]),5)
            self.assertEqual(len(result["sha256"]),5)

    def test_claim_button_letter_must_appear_on_victory(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            p=args[1]/"19_victory_banner.png"
            with Image.open(p) as src: bitmap=src.convert("RGB")
            put(bitmap,CLAIM_GLYPHS["B_claim"],DARK)
            bitmap.save(p)
            self.assertFalse(audit_claim(*args)["checks"][
                "real_victory_previews_claim_button_and_exact_8_exp_12_gella"])

    def test_claim_amount_exp_must_show_8(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            p=args[1]/"19_victory_banner.png"
            with Image.open(p) as src: bitmap=src.convert("RGB")
            put(bitmap,CLAIM_GLYPHS["EXP_8"],DARK)
            bitmap.save(p)
            self.assertFalse(audit_claim(*args)["checks"][
                "real_victory_previews_claim_button_and_exact_8_exp_12_gella"])

    def test_gella_last_digit_must_show_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            p=args[1]/"19_victory_banner.png"
            with Image.open(p) as src: bitmap=src.convert("RGB")
            put(bitmap,CLAIM_GLYPHS["GELLA_2"],DARK)
            bitmap.save(p)
            self.assertFalse(audit_claim(*args)["checks"][
                "real_victory_previews_claim_button_and_exact_8_exp_12_gella"])

    def test_preview_must_not_appear_before_finishing_burst(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            p=args[1]/"18_victory_reload.png"
            with Image.open(p) as src: bitmap=src.convert("RGB")
            put(bitmap,CLAIM_GLYPHS["B_claim"],GREEN)
            bitmap.save(p)
            self.assertFalse(audit_claim(*args)["checks"][
                "green_claim_label_is_absent_before_finishing_burst"])

    def test_preview_must_disappear_on_reentry_and_normal_battle(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            p=args[1]/"21_victory_reopen_rewards.png"
            with Image.open(p) as src: bitmap=src.convert("RGB")
            put(bitmap,CLAIM_GLYPHS["B_claim"],GREEN)
            bitmap.save(p)
            self.assertFalse(audit_claim(*args)["checks"][
                "claimed_and_reentered_unwon_battles_hide_pending_claim"])
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            p=args[0]/"01_baseline_r_battle.png"
            with Image.open(p) as src: bitmap=src.convert("RGB")
            put(bitmap,CLAIM_GLYPHS["B_claim"],GREEN)
            bitmap.save(p)
            self.assertFalse(audit_claim(*args)["checks"][
                "ordinary_r_battle_has_no_experimental_claim_prompt"])

    def test_missing_real_screenshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=claim_fixture(tmp)
            (args[1]/"19_victory_banner.png").unlink()
            with self.assertRaises(ValueError):
                audit_claim(*args)


if __name__=="__main__":
    unittest.main()
