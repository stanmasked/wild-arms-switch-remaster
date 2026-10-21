#!/usr/bin/env python3
"""Stage398: strict Xvfb NeXium UI controls-hint evidence.

Inputs must be screenshots of actual independent NeXium guest sessions.
Synthetic fixtures are for the companion unit tests ONLY.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_guest import GOLD
from audit_nexium_field_journal import native_pixel, read_rgb

WHITE=(246,247,252)
PROMPT_POSITIONS={
    "X_FIRE":(944+20,622+65),
    "MINUS":(944+20+8*13,622+65),
    "RELOAD":(944+20+14*13,622+65),
    "LAST_D":(944+20+19*13,622+65),
}
RIGHT_BORDER=(944+286-4,622+65)
MAIN_SHOTS=("01_baseline_r_battle",
            "03_arm_full","04_arm_fired","06_arm_reloaded")
REBOOT_SHOT="10_arm_restart_full"


def controls_pixels(image):
    return (all(native_pixel(image,*point)==WHITE
                for point in PROMPT_POSITIONS.values())
            and native_pixel(image,*RIGHT_BORDER)==GOLD)


def audit_controls(main_shots,reboot_shots,report):
    main_shots,reboot_shots=Path(main_shots),Path(reboot_shots)
    files={name:main_shots/(name+".png") for name in MAIN_SHOTS}
    files[REBOOT_SHOT]=reboot_shots/(REBOOT_SHOT+".png")
    if not all(path.is_file() for path in files.values()):
        missing=[name for name,path in files.items() if not path.is_file()]
        raise ValueError(f"real NeXium screenshots missing: {missing}")
    images={name:read_rgb(path) for name,path in files.items()}
    checks={
        "ordinary_r_battle_has_no_arm_prompt":
            all(native_pixel(images["01_baseline_r_battle"],*point)!=WHITE
                for point in PROMPT_POSITIONS.values()),
        "arm_full_magazine_shows_x_fire_minus_reload":
            controls_pixels(images["03_arm_full"]),
        "arm_spent_ammo_still_shows_fire_reload_controls":
            controls_pixels(images["04_arm_fired"]),
        "arm_reloaded_still_shows_same_controls":
            controls_pixels(images["06_arm_reloaded"]),
        "third_guest_cold_boot_shows_same_controls":
            controls_pixels(images[REBOOT_SHOT]),
    }
    result={
        "kind":"stage398_actual_nexium_arm_controls_pixels",
        "scope":"experimental_asset_free_switch_nro",
        "checks":checks,
        "all_checks_passed":all(checks.values()),
        "prompt":"X FIRE  MINUS RELOAD",
        "images_sha256":{
            name:hashlib.sha256(path.read_bytes()).hexdigest()
            for name,path in files.items()
        },
    }
    output=Path(report)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                      encoding="utf-8")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main-shots",type=Path,required=True)
    p.add_argument("--reboot-shots",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    args=p.parse_args()
    try:
        result=audit_controls(args.main_shots,args.reboot_shots,args.report)
    except (OSError,ValueError,TypeError) as exc:
        p.exit(2,f"NeXium ARM controls auditor rejected input: {exc}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1,"ARM input hints did not match actual NeXium screenshots\n")
