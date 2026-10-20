#!/usr/bin/env python3
"""Stage 363: verify real earned EXP/Gella survive a fresh NeXium process.

Independent evidence: five guest Xvfb PNGs and immutable WABJ files
copied from guest SDMC. All rewards here are ROM-free prototype values.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal

NAMES = (
    "00_manual_before_win", "01_real_victory",
    "02_first_guest_reward_panel", "03_reboot_reward_panel",
    "04_reboot_after_retreat",
)
MAP = (63, 191, 138)
GOLD = (245, 183, 66)
GREEN = (63, 191, 138)
PANEL = (31, 45, 66)
DARK = (12, 19, 31)


def same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def audit_rewards(screens, first_a, final_a, final_b, output):
    screens = Path(screens)
    files = {p.name for p in screens.glob("*.png")}
    expected = {n + ".png" for n in NAMES}
    if files != expected:
        raise ValueError(f"expected exactly five guest PNGs: {sorted(files ^ expected)}")
    frames = {n: read_rgb(screens / (n + ".png")) for n in NAMES}
    field, victory, earned, reloaded, exited = (frames[n] for n in NAMES)
    original = read_journal(first_a)
    a = read_journal(final_a)
    b = read_journal(final_b)
    bytes_first = Path(first_a).read_bytes()
    bytes_a = Path(final_a).read_bytes()
    lower_panel = (*screen_point(680, 602), *screen_point(1250, 712))
    checks = {
        "first_guest_manually_started_with_original_map":
            native_pixel(field, 0, 5) == MAP
            and native_pixel(field, 690, 612) != GOLD,
        "real_seven_controller_attacks_produced_victory":
            native_pixel(victory, 320, 294) == GREEN
            and native_pixel(victory, 700, 249) == DARK,
        "victory_on_B_committed_only_eight_EXP_and_twelve_Gella":
            original["generation"] == 1 and original["outcome"] == 1
            and original["wins"] == 1 and original["losses"] == 0
            and original["retreats"] == 0 and original["experience"] == 8
            and original["gella"] == 12,
        "first_guest_ZL_renders_WIN_1_EXP_8_G_12":
            native_pixel(earned, 690, 612) == GOLD
            and native_pixel(earned, 780, 656) == GOLD
            and native_pixel(earned, 776, 656) == PANEL
            and native_pixel(earned, 1015, 629) == GREEN
            and native_pixel(earned, 1080, 625) == GREEN
            and native_pixel(earned, 1091, 635) == GREEN,
        "new_guest_shows_identical_earned_history_before_fighting":
            same(earned, reloaded, GAME_ROI)
            and native_pixel(reloaded, 1015, 629) == GREEN
            and native_pixel(reloaded, 1080, 625) == GREEN,
        "second_guest_retreat_returns_to_identical_original_map":
            native_pixel(exited, 0, 5) == MAP
            and same(field, exited, GAME_ROI)
            and same(field, exited, lower_panel),
        "next_generation_kept_rewards_and_added_no_duplicated_victory":
            b["generation"] == 2 and b["outcome"] == 3
            and b["wins"] == 1 and b["losses"] == 0
            and b["retreats"] == 1 and b["experience"] == 8
            and b["gella"] == 12,
        "first_valid_generation_remains_bit_for_bit_unchanged":
            bytes_first == bytes_a and a == original,
    }
    report = {
        "kind": "two_real_NeXium_guests_with_earned_victory_EXP_Gella",
        "provenance": "seven_real_combat_A_inputs_then_two_independent_SDMC_guest_processes",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journals": {"first": original, "committed_a": a, "committed_b": b},
        "sha256": {
            **{n: hashlib.sha256((screens / (n + ".png")).read_bytes()).hexdigest()
               for n in NAMES},
            "first_a": hashlib.sha256(bytes_first).hexdigest(),
            "committed_a": hashlib.sha256(bytes_a).hexdigest(),
            "committed_b": hashlib.sha256(Path(final_b).read_bytes()).hexdigest(),
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
    parser.add_argument("--first-a", type=Path, required=True)
    parser.add_argument("--final-a", type=Path, required=True)
    parser.add_argument("--final-b", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_rewards(args.screenshots, args.first_a, args.final_a,
                               args.final_b, args.report)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"NeXium earned reward persistence audit rejected: {exc}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "Actual guest earned-reward evidence does not match\n")
