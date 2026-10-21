#!/usr/bin/env python3
"""Stage399: actual third NeXium guest Burst + held ZR pixel audit."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_guest import (
    ARM_BORDER, ARM_FULL_BAR, GOLD, DARK, BLUE,
    same_game, same_arm_panel,
)
from audit_nexium_field_journal import native_pixel, read_rgb

NAMES=("12_arm_burst_fired","13_arm_burst_held")
# 1 of 3: floor(220/3)=73 gold pixels, next 147 are dark.
ONE_ROUND_LAST=(944+20+72,622+38)
ONE_ROUND_FIRST_EMPTY=(944+20+73,622+38)
ZR_HINT=(944+174,622+14)
FOE_0_HEALTH=(692+100,249)


def audit_burst(original_shots, cold_shots, burst_shots, report):
    original_shots=Path(original_shots)
    cold_shots=Path(cold_shots)
    burst_shots=Path(burst_shots)
    if {p.name for p in burst_shots.glob("*.png")}!={
        name+".png" for name in NAMES
    }:
        raise ValueError("unexpected or absent real Burst guest frame(s)")
    sources={
        "initial":original_shots/"03_arm_full.png",
        "cold":cold_shots/"10_arm_restart_full.png",
        "return":cold_shots/"11_arm_restart_return.png",
        "field":cold_shots/"09_arm_restart_field.png",
        "fired":burst_shots/(NAMES[0]+".png"),
        "held":burst_shots/(NAMES[1]+".png"),
    }
    missing=[name for name,file in sources.items() if not file.is_file()]
    if missing:
        raise ValueError(f"missing actual NeXium frame: {missing}")
    images={name:read_rgb(path) for name,path in sources.items()}
    initial,cold,fired,held=(images[name] for name in
                             ("initial","cold","fired","held"))
    checks={
        "burst_starts_from_full_three_of_three":
            native_pixel(cold,*ARM_FULL_BAR)==GOLD
            and native_pixel(cold,*FOE_0_HEALTH)!=DARK,
        "zr_hint_visible_on_full_and_one_round_hud":
            native_pixel(cold,*ZR_HINT)==GOLD
            and native_pixel(fired,*ZR_HINT)==GOLD
            and native_pixel(held,*ZR_HINT)==GOLD,
        "burst_spent_exactly_two_bullets":
            native_pixel(fired,*ARM_BORDER)==GOLD
            and native_pixel(fired,*ONE_ROUND_LAST)==GOLD
            and native_pixel(fired,*ONE_ROUND_FIRST_EMPTY)==DARK
            and native_pixel(fired,*ARM_FULL_BAR)==DARK,
        "burst_one_turn_defeats_initial_14_hp_foe":
            native_pixel(fired,*FOE_0_HEALTH)==DARK
            and not same_game(cold,fired),
        "held_zr_does_not_refire_or_change_ui":
            same_game(fired,held)
            and same_arm_panel(fired,held)
            and native_pixel(held,*ONE_ROUND_LAST)==GOLD
            and native_pixel(held,*ONE_ROUND_FIRST_EMPTY)==DARK,
        "normal_arm_opening_unchanged":
            same_game(initial,cold)
            and same_arm_panel(initial,cold),
        "b_return_to_identical_original_field":
            same_game(images["field"],images["return"]),
    }
    payload={
        "kind":"stage399_real_nexium_zr_burst_guest_pixels",
        "checks":checks,"all_checks_passed":all(checks.values()),
        "sha256":{k:hashlib.sha256(v.read_bytes()).hexdigest()
                  for k,v in sources.items()},
    }
    output=Path(report)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",
                      encoding="utf-8")
    return payload


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-shots",type=Path,required=True)
    parser.add_argument("--cold-shots",type=Path,required=True)
    parser.add_argument("--burst-shots",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    a=parser.parse_args()
    try:
        result=audit_burst(a.main_shots,a.cold_shots,a.burst_shots,a.report)
    except (ValueError,TypeError,OSError) as exc:
        parser.exit(2,f"NeXium Burst audit rejected: {exc}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1,"Actual NeXium Burst pixel audit failed\n")
