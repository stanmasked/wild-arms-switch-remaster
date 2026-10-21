#!/usr/bin/env python3
"""Stage401: validate a fourth REAL NeXium process awarding Burst victory once.

Host-created PNG test fixtures are only unit tests; passing them is NOT
proof of running NeXium. The live guest workflow captures these exact files.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_guest import (
    ARM_FULL_BAR, ARM_PARTIAL_BAR, ARM_PAST_PARTIAL,
    GOLD, DARK, MAP_STATUS, RED, same_game, battle_slots
)
from audit_nexium_arm_cold_boot import valid_terminated
from audit_nexium_field_journal import native_pixel, read_rgb

GREEN=MAP_STATUS

NAMES=(
    "14_victory_field",
    "15_victory_full",
    "16_victory_first_burst",
    "17_victory_melee",
    "18_victory_reload",
    "19_victory_banner",
    "20_victory_return",
    "21_victory_reopen_rewards",
    "22_victory_second_reopen",
)
ONE_LAST=(944+20+72,622+38)
ONE_EMPTY=(944+20+73,622+38)
FOE_0=(692+100,249)
FOE_1_ALIVE=(692+240,491)
FOE_1_SPENT=(692+270,491)
FOE_1_DOWN=(692+100,491)
VICTORY_BORDER=(320,294)
EXP_START=(70,667)
EXP_8_MIDDLE=(70+4*13+2,667+6)
GELLA_1=(70+13*13+4,667)
GELLA_2=(70+14*13+2,667)
WINS_ONE=(70+2*13+4,687)


def balance_pixels(frame):
    return all(native_pixel(frame,*point)==GREEN
               for point in (EXP_START,EXP_8_MIDDLE,GELLA_1,GELLA_2)) and (
               native_pixel(frame,*WINS_ONE)==GOLD)


def one_round(frame):
    return (native_pixel(frame,*ONE_LAST)==GOLD
            and native_pixel(frame,*ONE_EMPTY)==DARK
            and native_pixel(frame,*ARM_FULL_BAR)==DARK)


def audit_victory(shots,original_shots,processes_path,
                  cold_process_path,victory_process_path,victory_root,report):
    shots=Path(shots)
    actual={p.name for p in shots.glob("*.png")}
    expected={name+".png" for name in NAMES}
    if actual!=expected:
        raise ValueError(f"missing/extra victory guest screenshots: {actual ^ expected}")
    images={name:read_rgb(shots/(name+".png")) for name in NAMES}
    before,opened,burst,melee,reloaded,won,returned,reenter,reenter_again=[
        images[name] for name in NAMES
    ]
    original_shots=Path(original_shots)
    initial=read_rgb(original_shots/"00_baseline_field.png")
    controls=read_rgb(original_shots/"03_arm_full.png")
    p=json.loads(Path(processes_path).read_text(encoding="utf-8"))
    c=json.loads(Path(cold_process_path).read_text(encoding="utf-8"))
    v=json.loads(Path(victory_process_path).read_text(encoding="utf-8"))
    required={"victory_pid","victory_wait_status",
              "victory_force_killed","victory_wait_completed"}
    if set(v)!=required:
        raise ValueError("missing/unexpected fourth-process exit evidence")
    pids=[p.get("baseline_pid"),p.get("arm_pid"),c.get("armrestart_pid"),
          v.get("victory_pid")]
    directory=battle_slots(victory_root)[0].parent
    mounted=directory.is_dir() and not directory.is_symlink()
    files=list(directory.iterdir()) if mounted else []
    checks={
        "four_independent_real_nexium_guest_processes":
            all(type(pid) is int and pid>0 for pid in pids)
            and len(set(pids))==4
            and v["victory_wait_completed"] is True
            and valid_terminated(v,"victory"),
        "victory_guest_fresh_field_and_unspent_arm":
            same_game(initial,before)
            and same_game(controls,opened)
            and native_pixel(opened,*ARM_FULL_BAR)==GOLD
            and native_pixel(opened,*FOE_0)==RED,
        "first_zr_burst_kills_first_foe_and_spends_two":
            one_round(burst)
            and native_pixel(burst,*FOE_0)==DARK
            and native_pixel(burst,*FOE_1_ALIVE)==RED,
        "regular_a_melee_reduces_second_foe_to_thirteen_hp":
            one_round(melee)
            and native_pixel(melee,*FOE_1_ALIVE)==RED
            and native_pixel(melee,*FOE_1_SPENT)==DARK,
        "minus_reload_refills_ammo_before_finisher":
            native_pixel(reloaded,*ARM_FULL_BAR)==GOLD
            and native_pixel(reloaded,*FOE_1_SPENT)==DARK,
        "second_zr_burst_ends_in_real_victory":
            one_round(won)
            and native_pixel(won,*FOE_0)==DARK
            and native_pixel(won,*FOE_1_DOWN)==DARK
            and native_pixel(won,*VICTORY_BORDER)==GREEN,
        "b_exit_restores_exact_prebattle_field":
            same_game(returned,before)
            and same_game(returned,initial),
        "reentry_displays_exact_eight_exp_twelve_gella_one_win":
            balance_pixels(reenter)
            and native_pixel(reenter,*ARM_FULL_BAR)==GOLD
            and native_pixel(reenter,*FOE_0)==RED
            and native_pixel(reenter,*FOE_1_ALIVE)==RED,
        "second_reentry_after_unwon_b_retreat_never_double_awards":
            balance_pixels(reenter_again)
            and native_pixel(reenter_again,*ARM_FULL_BAR)==GOLD
            and native_pixel(reenter_again,*FOE_0)==RED,
        "fourth_guest_sdmc_never_creates_any_save_or_temp":
            mounted and not files,
    }
    result={
        "kind":"stage401_real_fourth_nexium_guest_burst_victory_rewards",
        "checks":checks,
        "all_checks_passed":all(checks.values()),
        "sha256":{name:hashlib.sha256((shots/(name+".png")).read_bytes()).hexdigest()
                  for name in NAMES},
        "scope":"synthetic_rom_free_volatile_arm_rewards_no_user_files",
    }
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ("shots","original-shots","processes","cold-process",
                "victory-process","victory-root","report"):
        ap.add_argument("--"+arg,required=True,type=Path)
    a=ap.parse_args()
    try:
        result=audit_victory(a.shots,a.original_shots,a.processes,
            a.cold_process,a.victory_process,a.victory_root,a.report)
    except (OSError,ValueError,TypeError,KeyError) as err:
        ap.exit(2,f"NeXium Burst victory auditor rejected: {err}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        ap.exit(1,"Actual NeXium Burst victory proof failed\n")
