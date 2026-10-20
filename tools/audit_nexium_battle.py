#!/usr/bin/env python3
"""Strict independent audit of real NeXium Xvfb battle inputs.

Stage 343: homebrew guest pixels, NOT a framebuffer dump, PS1 assets,
or a native Nintendo Switch hardware test. Every accepted image is
from the same independently restarted NeXium guest process.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI
from audit_nexium_field_journal import read_rgb, native_pixel

SCREENSHOTS = (
    "00_field_before", "01_battle_open", "02_after_strike",
    "03_strike_held", "04_after_guard", "05_field_return",
)
BLUE = (105, 160, 230)
GOLD = (245, 183, 66)
RED = (201, 67, 76)
DARK = (12, 19, 31)
MAP_STATUS = (63, 191, 138)


def same_game_roi(a, b):
    return ImageChops.difference(
        a.crop(GAME_ROI), b.crop(GAME_ROI)).getbbox() is None


def audit_battle(directory, report):
    directory = Path(directory)
    files = {p.name for p in directory.glob("*.png")}
    expected = {s + ".png" for s in SCREENSHOTS}
    if files != expected:
        raise ValueError(f"incorrect guest battle screenshot set: {sorted(files ^ expected)}")
    shots = {name: read_rgb(directory / (name + ".png"))
             for name in SCREENSHOTS}
    before, opened, hit, held, guarded, returned = (
        shots[name] for name in SCREENSHOTS
    )

    # Battle renderer uses 1280x720 native RGBA8 and is projected to
    # NeXium's fixed 1234x694 game viewport in a 1600x900 Xvfb desktop.
    checks = {
        "manual_field_before_battle":
            native_pixel(before, 0, 5) == MAP_STATUS,
        "r_opened_battle_in_guest":
            # The NeXium performance HUD covers the top-left corner
            # (native 70,120). Check TWO exposed pixels of the same
            # selected hero's left border instead of masking any frame.
            native_pixel(opened, 70, 220) == BLUE
            and native_pixel(opened, 70, 245) == BLUE
            and native_pixel(opened, 670, 165) == GOLD
            and native_pixel(opened, 692 + 230, 249) == RED,
        "a_strike_reduced_actual_foe_hp":
            native_pixel(hit, 692 + 180, 249) == RED
            and native_pixel(hit, 692 + 230, 249) == DARK
            and native_pixel(hit, 70, 284) == BLUE,
        "held_a_did_not_trigger_another_action":
            same_game_roi(hit, held),
        "y_guard_selected_third_hero_without_extra_hit":
            native_pixel(guarded, 70, 448) == BLUE
            and native_pixel(guarded, 692 + 180, 249) == RED
            and native_pixel(guarded, 692 + 230, 249) == DARK,
        "b_returned_to_exact_same_field_pixels":
            same_game_roi(before, returned)
            and native_pixel(returned, 0, 5) == MAP_STATUS,
    }
    result = {
        "kind": "real_nexium_sixth_process_battle_input_audit",
        "provenance": "emulator_xvfb_desktop_not_hardware_or_native_framebuffer",
        "checks": checks,
        "battle_open_probe_rgb": {
            "selected_hero_border": native_pixel(opened, 70, 120),
            "selected_foe_border": native_pixel(opened, 670, 165),
            "full_foe_health_bar": native_pixel(opened, 692 + 230, 249),
            "map_status_before": native_pixel(before, 0, 5),
        },
        "all_checks_passed": all(checks.values()),
        "sha256": {
            name: hashlib.sha256((directory / (name + ".png")).read_bytes()).hexdigest()
            for name in SCREENSHOTS
        },
    }
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    options = parser.parse_args()
    try:
        result = audit_battle(options.screenshots, options.report)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Guest battle audit rejected: {error}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "Real guest battle screenshot check failed\n")
