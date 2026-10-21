#!/usr/bin/env python3
"""Stage400: real Xvfb HUD readiness pixel oracle, never synthetic guest proof."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_guest import DARK, GOLD
from audit_nexium_field_journal import native_pixel, read_rgb

GREEN=(63,191,138)
PANEL=(31,45,66)
# Battle font first B glyph and seventh glyph's upper row:
# READY has an R (column 1 lit), NEED has an N (column 4 lit).
STATUS_B=(944+20,622+48)
READY_R=(944+20+6*13+2,622+48)
NEED_N=(944+20+6*13+8,622+48)


def ready(img):
    return (native_pixel(img,*STATUS_B)==GREEN and
            native_pixel(img,*READY_R)==GREEN and
            native_pixel(img,*NEED_N)==PANEL)


def need_two(img):
    return (native_pixel(img,*STATUS_B)==GOLD and
            native_pixel(img,*READY_R)==PANEL and
            native_pixel(img,*NEED_N)==GOLD)


def audit_readiness(original_shots,cold_shots,burst_shots,report):
    original_shots=Path(original_shots)
    cold_shots=Path(cold_shots)
    burst_shots=Path(burst_shots)
    paths={
        "ordinary":original_shots/"01_baseline_r_battle.png",
        "full":original_shots/"03_arm_full.png",
        "fired":original_shots/"04_arm_fired.png",
        "reloaded":original_shots/"06_arm_reloaded.png",
        "reboot":cold_shots/"10_arm_restart_full.png",
        "burst":burst_shots/"12_arm_burst_fired.png",
        "held":burst_shots/"13_arm_burst_held.png",
    }
    missing=[k for k,v in paths.items() if not v.is_file()]
    if missing:
        raise ValueError(f"missing Xvfb guest screenshots: {missing}")
    images={key:read_rgb(file) for key,file in paths.items()}
    normal=images["ordinary"]
    checks={
        "ordinary_r_has_no_burst_readiness_overlay":
            native_pixel(normal,*STATUS_B) not in (GREEN,GOLD),
        "full_three_of_three_burst_ready_green":ready(images["full"]),
        "after_one_x_fire_two_of_three_still_ready":ready(images["fired"]),
        "after_minus_reload_three_of_three_ready":ready(images["reloaded"]),
        "cold_boot_full_three_of_three_ready":ready(images["reboot"]),
        "after_zr_burst_one_of_three_need_two_gold":need_two(images["burst"]),
        "holding_zr_keeps_need_two_gold":need_two(images["held"]),
    }
    result={
        "kind":"stage400_real_nexium_dynamic_arm_burst_readiness",
        "scope":"compile-gated_asset-free_homebrew",
        "checks":checks,
        "all_checks_passed":all(checks.values()),
        "sha256":{k:hashlib.sha256(path.read_bytes()).hexdigest()
                  for k,path in paths.items()},
    }
    target=Path(report)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                      encoding="utf-8")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-shots",type=Path,required=True)
    p.add_argument("--cold-shots",type=Path,required=True)
    p.add_argument("--burst-shots",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    try:
        result=audit_readiness(a.original_shots,a.cold_shots,
                               a.burst_shots,a.report)
    except (ValueError,TypeError,OSError) as err:
        p.exit(2,f"ARM readiness auditor rejected: {err}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1,"Real NeXium ARM Burst readiness pixels failed\n")
