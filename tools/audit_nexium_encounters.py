#!/usr/bin/env python3
"""Stage 350: independent observed-Xvfb proof of optional ZR encounters.

Screenshots must come from a SEVENTH, isolated real NeXium guest process,
not the host battle preview. Only fixed, unobscured game pixels count.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI
from audit_nexium_field_journal import read_rgb, native_pixel

NAMES = (
    "00_field_start", "01_zr_enabled", "02_event_pending",
    "03_event_acknowledged", "04_encounter_open",
    "05_encounter_strike", "06_field_return",
)
FIELD_OK = (63, 191, 138)
FIELD_EVENT = (246, 183, 66)
GOLD = (245, 183, 66)
BLUE = (105, 160, 230)
RED = (201, 67, 76)
DARK = (12, 19, 31)
SPRITE = (201, 67, 76)


def game_roi_equal(a, b):
    return ImageChops.difference(
        a.crop(GAME_ROI), b.crop(GAME_ROI)).getbbox() is None


def audit_encounter(folder: Path, output: Path):
    folder = Path(folder)
    actual = {p.name for p in folder.glob("*.png")}
    expected = {n + ".png" for n in NAMES}
    if actual != expected:
        raise ValueError(f"seventh guest must supply exactly seven PNGs: "
                         f"{sorted(expected ^ actual)}")
    shots = {n: read_rgb(folder / (n + ".png")) for n in NAMES}
    start, enabled, pending, acked, battle, strike, returned = (
        shots[n] for n in NAMES
    )

    # ZR indicator at (1245,25) is deliberately outside the old field
    # reference ROI. FPS overlay obscures top-left battle hero at (70,120);
    # use exposed hero border y=220/245 instead, as in Stage 347.
    checks = {
        "default_opt_out_before_ZR":
            native_pixel(start, 0, 5) == FIELD_OK
            and native_pixel(start, 1245, 25) != GOLD,
        "ZR_enabled_without_moving_or_mutating_field":
            native_pixel(enabled, 1245, 25) == GOLD
            and native_pixel(enabled, 0, 5) == FIELD_OK
            and game_roi_equal(start, enabled),
        "third_tile_paused_field_event_no_premature_battle":
            native_pixel(pending, 0, 5) == FIELD_EVENT
            and native_pixel(pending, 1245, 25) == GOLD
            and native_pixel(pending, 70, 220) != BLUE,
        "A_acknowledges_event_before_any_encounter":
            native_pixel(acked, 0, 5) == FIELD_OK
            and native_pixel(acked, 1245, 25) == GOLD
            and native_pixel(acked, 70, 220) != BLUE,
        "fourth_real_step_opens_selected_battle":
            native_pixel(battle, 70, 220) == BLUE
            and native_pixel(battle, 70, 245) == BLUE
            and native_pixel(battle, 670, 165) == GOLD
            and native_pixel(battle, 922, 249) == RED,
        "A_damage_only_inside_battle":
            native_pixel(strike, 70, 284) == BLUE
            and native_pixel(strike, 872, 249) == RED
            and native_pixel(strike, 922, 249) == DARK,
        "B_returns_to_moved_field_and_keeps_ZR_mode":
            native_pixel(returned, 0, 5) == FIELD_OK
            and native_pixel(returned, 1245, 25) == GOLD
            and native_pixel(returned, 500, 220) == SPRITE
            and not game_roi_equal(acked, returned),
    }
    report = {
        "kind": "nexium_seventh_guest_zr_step_encounter",
        "provenance": "actual_guest_xvfb_screenshots_not_switch_hardware",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "probe_rgb": {
            "opt_in_indicator": native_pixel(enabled, 1245, 25),
            "pending_event_status": native_pixel(pending, 0, 5),
            "acknowledged_status": native_pixel(acked, 0, 5),
            "battle_selected_hero": native_pixel(battle, 70, 220),
            "battle_selected_foe": native_pixel(battle, 670, 165),
            "battle_foe_hp_full": native_pixel(battle, 922, 249),
            "returned_player_sprite": native_pixel(returned, 500, 220),
        },
        "sha256": {
            n: hashlib.sha256((folder / (n + ".png")).read_bytes()).hexdigest()
            for n in NAMES
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_encounter(args.screenshots, args.report)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Seventh real guest audit rejected: {error}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "Seventh real guest encounter pixels do not match\n")
