#!/usr/bin/env python3
"""Stage 356: observe the opt-in ZL battle history in a real eighth NeXium guest.

Accept strictly the seven chronological Xvfb screenshots from one boot.
No in-memory counter, save, host framebuffer, or generated PNG is trusted.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel

FIELD_UNOBSCURED_ROI = (260, 130, 1000, 580)  # panel begins at desktop y~590

NAMES = (
    "00_field_start", "01_zl_empty", "02_first_battle",
    "03_field_after_retreat", "04_zl_retreat",
    "05_zl_released", "06_next_battle",
)
MAP = (63, 191, 138)
GOLD = (245, 183, 66)
BLUE = (105, 160, 230)
WHITE = (246, 247, 252)
PANEL = (31, 45, 66)


def same_region(a, b, roi):
    return ImageChops.difference(a.crop(roi), b.crop(roi)).getbbox() is None


def audit_history(folder, output):
    folder = Path(folder)
    files = {p.name for p in folder.glob("*.png")}
    expected = {n + ".png" for n in NAMES}
    if files != expected:
        raise ValueError(f"history screenshots mismatch: {sorted(files ^ expected)}")
    shots = {n: read_rgb(folder / (n + ".png")) for n in NAMES}
    before, empty, battle, returned, retreat, released, next_battle = (
        shots[n] for n in NAMES
    )
    # The optional HUD overlaps the bottom of the legacy GAME_ROI and away
    # from the emulator's top-left FPS/debug overlay. Compare unchanged field pixels above y580, and the exact
    # lower panel region only on frames where ZL is not held.
    panel_region = (*screen_point(680, 602), *screen_point(1250, 712))

    # "EXITS 0  LAST NONE" or "EXITS 1  LAST RETREAT" starts x=711,y=677.
    # Text stride is 13 pixels, font is 5x7 with 2x2 raster glyph dots:
    # at digit start x=789, row2 y=681, '0' lights col0 but not col2;
    # '1' lights col2 but not col0. Compare independent full-color dots.
    checks = {
        "manual_field_starts_without_history_overlay":
            native_pixel(before, 0, 5) == MAP
            and native_pixel(before, 690, 612) != GOLD,
        "ZL_renders_zero_retreat_count_on_same_field":
            native_pixel(empty, 690, 612) == GOLD
            and native_pixel(empty, 789, 681) == WHITE
            and native_pixel(empty, 793, 681) == PANEL
            and same_region(before, empty, FIELD_UNOBSCURED_ROI),
        "R_opens_first_combat_without_previous_history":
            native_pixel(battle, 70, 220) == BLUE
            and native_pixel(battle, 230, 691) != GOLD,
        "B_records_retreat_without_overlay_or_field_movement":
            same_region(before, returned, GAME_ROI)
            and same_region(before, returned, panel_region)
            and native_pixel(returned, 0, 5) == MAP,
        "next_ZL_panel_shows_exactly_one_retreat":
            native_pixel(retreat, 690, 612) == GOLD
            and native_pixel(retreat, 789, 681) == PANEL
            and native_pixel(retreat, 793, 681) == WHITE
            and native_pixel(retreat, 923, 679) == WHITE
            and same_region(before, retreat, FIELD_UNOBSCURED_ROI),
        "releasing_ZL_restores_the_exact_original_field":
            same_region(before, released, GAME_ROI)
            and same_region(before, released, panel_region),
        "new_battle_retains_record_with_fresh_combat":
            native_pixel(next_battle, 70, 220) == BLUE
            and native_pixel(next_battle, 230, 691) == GOLD
            and native_pixel(next_battle, 922, 249) == (201, 67, 76),
    }
    report = {
        "kind": "real_nexium_eighth_guest_battle_result_history",
        "provenance": "actual_guest_xvfb_not_native_framebuffer_or_switch_hardware",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "probes": {
            "empty_zero_left": native_pixel(empty, 789, 681),
            "empty_zero_middle": native_pixel(empty, 793, 681),
            "record_one_left": native_pixel(retreat, 789, 681),
            "record_one_middle": native_pixel(retreat, 793, 681),
            "next_battle_footer_one": native_pixel(next_battle, 230, 691),
        },
        "sha256": {
            n: hashlib.sha256((folder / (n + ".png")).read_bytes()).hexdigest()
            for n in NAMES
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_history(args.screenshots, args.report)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"Eighth guest battle history rejected: {exc}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "Actual guest battle result screenshot mismatch\n")
