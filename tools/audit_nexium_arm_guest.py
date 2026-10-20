#!/usr/bin/env python3
"""Stage390: strict real-Xvfb NeXium opt-in ARM pixels + isolated SDMC audit.

Do not use this report as proof unless all screenshots originate from the
corresponding actual emulator launches. Synthetic fixtures are for test-only.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops

from audit_nexium_checkpoints import GAME_ROI
from audit_nexium_field_journal import native_pixel, read_rgb

SCREENSHOTS = (
    "00_baseline_field",
    "01_baseline_r_battle",
    "02_baseline_return",
    "03_arm_full",
    "04_arm_fired",
    "05_arm_fire_held",
    "06_arm_reloaded",
    "07_arm_return",
)
GOLD = (245, 183, 66)
BLUE = (105, 160, 230)
RED = (201, 67, 76)
DARK = (12, 19, 31)
MAP_STATUS = (63, 191, 138)
# Matches the exact host-side Stage387 opt-in raster locations.
ARM_BORDER = (944, 622)
ARM_FULL_BAR = (944 + 20 + 219, 622 + 38)
ARM_PARTIAL_BAR = (944 + 20 + 145, 622 + 38)
ARM_PAST_PARTIAL = (944 + 20 + 146, 622 + 38)


def same_game(a, b):
    return ImageChops.difference(a.crop(GAME_ROI), b.crop(GAME_ROI)).getbbox() is None


def battle_slots(data_root):
    directory = Path(data_root) / "sdmc" / "switch" / "wild_arms_field"
    return [directory / "battle-progress.a", directory / "battle-progress.b"]


def audit_arm_guests(screenshots, baseline_root, arm_root, processes, report):
    screenshots = Path(screenshots)
    actual = {p.name for p in screenshots.glob("*.png")}
    expected = {name + ".png" for name in SCREENSHOTS}
    if actual != expected:
        raise ValueError(f"missing/unexpected screenshot(s): {sorted(actual ^ expected)}")
    baseline_root, arm_root = Path(baseline_root), Path(arm_root)
    if baseline_root.resolve() == arm_root.resolve():
        raise ValueError("baseline and ARM use aliased NeXium data roots")
    processes = json.loads(Path(processes).read_text(encoding="utf-8"))
    if set(processes) != {"baseline_pid", "arm_pid", "baseline_wait_completed",
                          "arm_wait_completed"}:
        raise ValueError("unknown or missing process evidence")
    if not all(type(processes[key]) is int and processes[key] > 0
               for key in ("baseline_pid", "arm_pid")):
        raise ValueError("missing distinct positive NeXium process IDs")

    images = {name: read_rgb(screenshots / (name + ".png"))
              for name in SCREENSHOTS}
    field, plain, plain_return, full, fired, held, reloaded, arm_return = (
        images[name] for name in SCREENSHOTS
    )
    baseline_slots = battle_slots(baseline_root)
    arm_slots = battle_slots(arm_root)
    checks = {
        "two_independent_guest_processes":
            processes["baseline_pid"] != processes["arm_pid"]
            and processes["baseline_wait_completed"] is True
            and processes["arm_wait_completed"] is True,
        "ordinary_r_opens_unchanged_battle":
            native_pixel(field, 0, 5) == MAP_STATUS
            and native_pixel(plain, 70, 220) == BLUE
            and native_pixel(plain, 670, 165) == GOLD
            and native_pixel(plain, *ARM_BORDER) != GOLD,
        "ordinary_r_return_exact_field_pixels":
            same_game(field, plain_return),
        "zl_plus_r_shows_full_arm_magazine":
            native_pixel(full, *ARM_BORDER) == GOLD
            and native_pixel(full, *ARM_FULL_BAR) == GOLD
            and native_pixel(full, 70, 220) == BLUE,
        "x_fire_spends_exactly_one_ammo_and_damages_real_enemy":
            native_pixel(fired, *ARM_BORDER) == GOLD
            and native_pixel(fired, *ARM_PARTIAL_BAR) == GOLD
            and native_pixel(fired, *ARM_PAST_PARTIAL) == DARK
            and native_pixel(fired, *ARM_FULL_BAR) == DARK
            and native_pixel(fired, 692 + 100, 249) == RED
            and native_pixel(fired, 692 + 230, 249) == DARK,
        "held_x_did_not_double_fire":
            same_game(fired, held)
            and native_pixel(held, *ARM_FULL_BAR) == DARK,
        "guard_two_heroes_then_minus_reloads_without_extra_damage":
            native_pixel(reloaded, *ARM_BORDER) == GOLD
            and native_pixel(reloaded, *ARM_FULL_BAR) == GOLD
            and native_pixel(reloaded, 692 + 100, 249) == RED
            and native_pixel(reloaded, 692 + 230, 249) == DARK,
        "b_exit_exactly_restores_field":
            same_game(field, arm_return)
            and native_pixel(arm_return, 0, 5) == MAP_STATUS,
        "normal_b_close_did_persist_in_isolated_baseline":
            any(path.is_file() and path.stat().st_size > 0 for path in baseline_slots),
        "arm_training_never_created_wabj_slots":
            not any(path.exists() or path.is_symlink() for path in arm_slots),
    }
    result = {
        "kind": "stage390_real_nexium_arm_training_guest_audit",
        "guest_capture_source": "actual_nexium_xvfb_screenshots_not_host_raster",
        "scope": "research_asset_free_nro_not_hardware",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "sha256": {
            name: hashlib.sha256((screenshots / (name + ".png")).read_bytes()).hexdigest()
            for name in SCREENSHOTS
        },
    }
    path = Path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--arm-root", type=Path, required=True)
    parser.add_argument("--processes", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = audit_arm_guests(args.screenshots, args.baseline_root,
                                 args.arm_root, args.processes, args.report)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"NeXium ARM audit rejected: {exc}\n")
    print(json.dumps(output["checks"], sort_keys=True))
    if not output["all_checks_passed"]:
        parser.exit(1, "Real NeXium ARM screen/journal audit failed\n")
