#!/usr/bin/env python3
"""Stage402: real NeXium Victory claim message pixel evidence.

Only authentic Xvfb screenshots from the 4th NeXium guest are acceptable
for live CI. Unit-test fixtures are separately identified as synthetic.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_guest import MAP_STATUS as GREEN
from audit_nexium_field_journal import native_pixel, read_rgb

# "B CLAIM EXP 8  GELLA 12" with the native 5x7 bitmap font,
# 13 horizontal pixels per glyph, green on the Victory popup.
ORIGIN_X,ORIGIN_Y=440,368
CLAIM_GLYPHS={
    "B_claim":(ORIGIN_X+2,ORIGIN_Y),
    "EXP_8":(ORIGIN_X+12*13+2,ORIGIN_Y),
    "GELLA_1":(ORIGIN_X+21*13+4,ORIGIN_Y),
    "GELLA_2":(ORIGIN_X+22*13+2,ORIGIN_Y),
}
RIGHT_MARGIN=(ORIGIN_X+23*13,ORIGIN_Y)
NAMES={
    "ordinary":"01_baseline_r_battle",
    "prewin":"18_victory_reload",
    "won":"19_victory_banner",
    "claimed":"21_victory_reopen_rewards",
    "reentered":"22_victory_second_reopen",
}


def audit_claim(ordinary_shots,victory_shots,report):
    ordinary_shots,victory_shots=Path(ordinary_shots),Path(victory_shots)
    files={
        key:(ordinary_shots if key=="ordinary" else victory_shots)
             /(filename+".png")
        for key,filename in NAMES.items()
    }
    missing=[key for key,path in files.items() if not path.is_file()]
    if missing: raise ValueError(f"genuine NeXium PNGs missing: {missing}")
    images={key:read_rgb(path) for key,path in files.items()}
    won=images["won"]
    checks={
        "real_victory_previews_claim_button_and_exact_8_exp_12_gella":
            all(native_pixel(won,*point)==GREEN
                for point in CLAIM_GLYPHS.values()),
        "green_claim_label_is_absent_before_finishing_burst":
            all(native_pixel(images["prewin"],*point)!=GREEN
                for point in CLAIM_GLYPHS.values()),
        "green_claim_label_does_not_bleed_outside_victory_box":
            native_pixel(won,*RIGHT_MARGIN)!=GREEN,
        "claimed_and_reentered_unwon_battles_hide_pending_claim":
            all(native_pixel(images[name],*point)!=GREEN
                for name in ("claimed","reentered")
                for point in CLAIM_GLYPHS.values()),
        "ordinary_r_battle_has_no_experimental_claim_prompt":
            all(native_pixel(images["ordinary"],*point)!=GREEN
                for point in CLAIM_GLYPHS.values()),
    }
    payload={
        "kind":"stage402_actual_ne_xium_victory_claim_prompt",
        "checks":checks,
        "all_checks_passed":all(checks.values()),
        "sha256":{name:hashlib.sha256(path.read_bytes()).hexdigest()
                  for name,path in files.items()},
    }
    target=Path(report)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",
                      encoding="utf-8")
    return payload


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ordinary-shots",type=Path,required=True)
    p.add_argument("--victory-shots",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    try:
        result=audit_claim(a.ordinary_shots,a.victory_shots,a.report)
    except (OSError,ValueError,TypeError) as err:
        p.exit(2,f"Stage402 guest preview audit rejected: {err}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1,"Actual NeXium Victory claim text audit failed\n")
