#!/usr/bin/env python3
"""Synthetic negative tests for Stage401, NEVER third-party emulator proof."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_nexium_arm_victory import (
    audit_victory,NAMES,ONE_LAST,ONE_EMPTY,FOE_0,
    FOE_1_ALIVE,FOE_1_SPENT,FOE_1_DOWN,VICTORY_BORDER,
    EXP_START,EXP_8_MIDDLE,GELLA_1,GELLA_2,WINS_ONE,GREEN
)
from audit_nexium_arm_guest import ARM_FULL_BAR,GOLD,DARK,RED
from test_audit_nexium_arm_cold_boot import cold_fixture
from test_audit_nexium_arm_guest import put
from test_audit_nexium_battle_two_victories import journal


def fixture_victory(root):
    root=Path(root)
    main,cold,processes,cold_process,_,_=cold_fixture(root)
    victory=root/"victory"
    victory.mkdir()
    sd=root/"victory-sdmc"/"sdmc/switch/wild_arms_field"
    sd.mkdir(parents=True)
    journal(sd/"arm-training-progress.a",1,1,1,0,8,12)
    journal(sd/"arm-training-progress.b",2,3,1,1,8,12)
    third=root/"victory-process.json"
    third.write_text(json.dumps({
        "victory_pid":1004,"victory_wait_status":143,
        "victory_force_killed":False,"victory_wait_completed":True}))
    opened=main/"03_arm_full.png"
    with Image.open(opened) as im:
        original=im.convert("RGB")
    put(original,FOE_0,RED)
    put(original,FOE_1_ALIVE,RED)
    original.save(opened)

    def copy_and_edit(name,source,edit=()):
        output=victory/(name+".png")
        shutil.copyfile(source,output)
        with Image.open(output) as im:
            frame=im.convert("RGB")
        for point,color in edit:
            put(frame,point,color)
        frame.save(output)
        return output

    field=main/"00_baseline_field.png"
    copy_and_edit(NAMES[0],field)
    full=copy_and_edit(NAMES[1],opened)
    burst=copy_and_edit(NAMES[2],full,(
        (ONE_LAST,GOLD),(ONE_EMPTY,DARK),(ARM_FULL_BAR,DARK),
        (FOE_0,DARK),(FOE_1_ALIVE,RED)))
    melee=copy_and_edit(NAMES[3],burst,(
        (FOE_1_ALIVE,RED),(FOE_1_SPENT,DARK)))
    copy_and_edit(NAMES[4],melee,((ARM_FULL_BAR,GOLD),))
    copy_and_edit(NAMES[5],burst,(
        (FOE_0,DARK),(FOE_1_DOWN,DARK),(VICTORY_BORDER,GREEN)))
    copy_and_edit(NAMES[6],field)
    credited=copy_and_edit(NAMES[7],full,(
        (EXP_START,GREEN),(EXP_8_MIDDLE,GREEN),
        (GELLA_1,GREEN),(GELLA_2,GREEN),(WINS_ONE,GOLD)))
    copy_and_edit(NAMES[8],credited)
    return victory,main,processes,cold_process,third,sd.parents[2],root/"victory-audit.json"


class ArmVictoryGuestContractTests(unittest.TestCase):
    def test_synthetic_victory_contract_never_claims_ne_xium(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=audit_victory(*fixture_victory(tmp))
            self.assertTrue(result["all_checks_passed"],result["checks"])
            self.assertEqual(len(result["checks"]),13)
            self.assertEqual(len(result["sha256"]),9)

    def test_victory_requires_second_enemy_actually_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            p=a[0]/(NAMES[5]+".png")
            with Image.open(p) as im: frame=im.convert("RGB")
            put(frame,FOE_1_DOWN,RED)
            frame.save(p)
            self.assertFalse(audit_victory(*a)["checks"][
                "winning_burst_second_enemy_hp_reaches_zero"])

    def test_real_victory_must_have_green_banner_border(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            path=a[0]/(NAMES[5]+".png")
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,VICTORY_BORDER,DARK)
            frame.save(path)
            result=audit_victory(*a)
            self.assertFalse(result["checks"]["actual_victory_overlay_is_green"])
            self.assertTrue(result["checks"]["second_zr_burst_spends_two_ammo"])
            self.assertTrue(result["checks"]["winning_burst_second_enemy_hp_reaches_zero"])

    def test_real_victory_must_expend_burst_ammunition(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            path=a[0]/(NAMES[5]+".png")
            with Image.open(path) as src:
                frame=src.convert("RGB")
            put(frame,ONE_EMPTY,GOLD)
            frame.save(path)
            result=audit_victory(*a)
            self.assertFalse(result["checks"]["second_zr_burst_spends_two_ammo"])
            self.assertTrue(result["checks"]["actual_victory_overlay_is_green"])

    def test_first_burst_must_expend_two_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            p=a[0]/(NAMES[2]+".png")
            with Image.open(p) as im: frame=im.convert("RGB")
            put(frame,ARM_FULL_BAR,GOLD)
            frame.save(p)
            self.assertFalse(audit_victory(*a)["checks"][
                "first_zr_burst_kills_first_foe_and_spends_two"])

    def test_reentry_reward_amount_is_not_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            p=a[0]/(NAMES[7]+".png")
            with Image.open(p) as im: frame=im.convert("RGB")
            put(frame,EXP_8_MIDDLE,DARK)
            frame.save(p)
            self.assertFalse(audit_victory(*a)["checks"][
                "reentry_displays_exact_eight_exp_twelve_gella_one_win"])

    def test_no_double_payout_after_second_reentry(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            p=a[0]/(NAMES[8]+".png")
            with Image.open(p) as im: frame=im.convert("RGB")
            put(frame,GELLA_2,DARK)
            frame.save(p)
            self.assertFalse(audit_victory(*a)["checks"][
                "second_reentry_after_unwon_b_retreat_never_double_awards"])

    def test_write_leak_into_regular_battle_namespace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            (a[5]/"sdmc/switch/wild_arms_field"/"battle-progress.a").write_bytes(b"x")
            self.assertFalse(audit_victory(*a)["checks"][
                "confirmed_results_use_only_separate_arm_progress_slots"])

    def test_duplicate_process_id_fails_independence(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            p=a[4]
            state=json.loads(p.read_text())
            state["victory_pid"]=1003
            p.write_text(json.dumps(state))
            self.assertFalse(audit_victory(*a)["checks"][
                "four_independent_real_nexium_guest_processes"])

    def test_missing_or_bad_png_fails_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            (a[0]/(NAMES[4]+".png")).unlink()
            with self.assertRaises(ValueError):
                audit_victory(*a)
        with tempfile.TemporaryDirectory() as tmp:
            a=fixture_victory(tmp)
            (a[0]/(NAMES[5]+".png")).write_bytes(b"invalid png")
            with self.assertRaises((ValueError,OSError)):
                audit_victory(*a)


if __name__=="__main__":
    unittest.main()
