#!/usr/bin/env python3
"""Stage390: strict real-Xvfb NeXium opt-in ARM pixels + isolated SDMC audit.

Do not use this report as proof unless all screenshots originate from the
corresponding actual emulator launches. Synthetic fixtures are for test-only.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from PIL import ImageChops

from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import native_pixel, read_rgb
from stage_verified_battle_backup import _journal_from_bytes

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


def same_arm_panel(a, b):
    # The ammo panel is outside GAME_ROI; compare its actual projected
    # NeXium pixels, not only a few bar samples or the game center.
    left, top = screen_point(944, 622)
    right, bottom = screen_point(1230, 706)
    return ImageChops.difference(
        a.crop((left, top, right + 1, bottom + 1)),
        b.crop((left, top, right + 1, bottom + 1)),
    ).getbbox() is None


def battle_slots(data_root):
    directory = Path(data_root) / "sdmc" / "switch" / "wild_arms_field"
    return [directory / "battle-progress.a", directory / "battle-progress.b"]


def read_arm_progress_slot(path):
    """Validate one 52-byte WABJ v1 slot from the isolated ARM progress namespace."""
    raw = Path(path).read_bytes()
    if len(raw) != 52:
        raise ValueError(f"unexpected WABJ slot length: {path}")
    if raw[:4] != b"WABJ":
        raise ValueError(f"bad WABJ magic: {path}")
    generation = struct.unpack_from("<Q", raw, 4)[0]
    if generation == 0 or zlib.crc32(raw[:48]) != struct.unpack_from("<I", raw, 48)[0]:
        raise ValueError(f"invalid outer WABJ generation/CRC: {path}")
    payload = raw[12:48]
    if payload[:4] != b"WABR" or payload[4] != 1:
        raise ValueError(f"unsupported WABR payload: {path}")
    if payload[6:8] != b"\\0\\0" or payload[28:32] != b"\\0\\0\\0\\0":
        raise ValueError(f"nonzero WABR reserved bytes: {path}")
    if zlib.crc32(payload[:32]) != struct.unpack_from("<I", payload, 32)[0]:
        raise ValueError(f"invalid inner WABR CRC: {path}")
    wins, losses, retreats, exp, gella = struct.unpack_from("<IIIII", payload, 8)
    return {
        "generation": generation,
        "last": payload[5],
        "wins": wins,
        "losses": losses,
        "retreats": retreats,
        "experience": exp,
        "gella": gella,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def valid_two_retreat_progress_generations(records):
    """Require the expected first retreat and the next cold-boot retreat."""
    first = records.get("arm-training-progress.a")
    latest = records.get("arm-training-progress.b")
    return (
        set(records) == {"arm-training-progress.a", "arm-training-progress.b"}
        and first is not None and latest is not None
        and first["generation"] == 1 and first["last"] == 3
        and first["wins"] == 0 and first["losses"] == 0
        and first["retreats"] == 1
        and first["experience"] == 0 and first["gella"] == 0
        and latest["generation"] == 2 and latest["last"] == 3
        and latest["wins"] == 0 and latest["losses"] == 0
        and latest["retreats"] == 2
        and latest["experience"] == 0 and latest["gella"] == 0
    )


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
                          "arm_wait_completed",
                          "baseline_wait_status", "arm_wait_status",
                          "baseline_force_killed", "arm_force_killed"}:
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
    baseline_dir = baseline_slots[0].parent
    arm_dir = arm_slots[0].parent
    # A missing ARM SDMC directory is NOT evidence of a clean directory.
    # The homebrew should have mounted and created its field root.
    arm_dir_valid = arm_dir.is_dir() and not arm_dir.is_symlink()
    baseline_dir_valid = baseline_dir.is_dir() and not baseline_dir.is_symlink()
    separate_game_directories = (
        arm_dir_valid and baseline_dir_valid
        and arm_dir.resolve() != baseline_dir.resolve()
    )
    arm_entries = list(arm_dir.iterdir()) if arm_dir_valid else []
    arm_names = {p.name for p in arm_entries}
    progress_records = {}
    for name in ("arm-training-progress.a", "arm-training-progress.b"):
        slot = arm_dir / name
        if slot.is_file() and not slot.is_symlink():
            try:
                progress_records[name] = read_arm_progress_slot(slot)
            except (OSError, ValueError):
                pass
    field_names = {
        "field-save.a", "field-save.b", "field-save.tmp",
    }
    # Stage405 persists a confirmed ARM exit to its own journal. The two
    # guest retreats must be present there; regular battle/field slots stay absent.
    baseline_records = []
    for slot in baseline_slots:
        if slot.is_file() and not slot.is_symlink():
            try:
                baseline_records.append(_journal_from_bytes(slot.read_bytes()))
            except ValueError:
                pass
    checks = {
        "two_independent_guest_processes":
            processes["baseline_pid"] != processes["arm_pid"]
            and processes["baseline_wait_completed"] is True
            and processes["arm_wait_completed"] is True
            and type(processes["baseline_wait_status"]) is int
            and type(processes["arm_wait_status"]) is int
            and type(processes["baseline_force_killed"]) is bool
            and type(processes["arm_force_killed"]) is bool
            and (
                (not processes["baseline_force_killed"]
                 and processes["baseline_wait_status"] in (0, 143))
                or (processes["baseline_force_killed"]
                    and processes["baseline_wait_status"] == 137)
            )
            and (
                (not processes["arm_force_killed"]
                 and processes["arm_wait_status"] in (0, 143))
                or (processes["arm_force_killed"]
                    and processes["arm_wait_status"] == 137)
            ),
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
            # The ARM panel lies BELOW GAME_ROI. Comparing only the
            # central gameplay region misses ammo-only held-fire bugs.
            same_game(fired, held)
            and same_arm_panel(fired, held)
            and native_pixel(held, *ARM_BORDER) == GOLD
            and native_pixel(held, *ARM_PARTIAL_BAR) == GOLD
            and native_pixel(held, *ARM_PAST_PARTIAL) == DARK
            and native_pixel(held, *ARM_FULL_BAR) == DARK,
        "guard_two_heroes_then_minus_reloads_without_extra_damage":
            native_pixel(reloaded, *ARM_BORDER) == GOLD
            and native_pixel(reloaded, *ARM_FULL_BAR) == GOLD
            and native_pixel(reloaded, 692 + 100, 249) == RED
            and native_pixel(reloaded, 692 + 230, 249) == DARK,
        "b_exit_exactly_restores_field":
            same_game(field, arm_return)
            and native_pixel(arm_return, 0, 5) == MAP_STATUS,
        "normal_b_close_wrote_valid_single_retreat_journal":
            any(record["retreats"] == 1 and record["wins"] == 0
                    and record["experience"] == 0 and record["gella"] == 0
                    for record in baseline_records),
        "arm_training_never_created_regular_battle_slots":
            arm_dir_valid and
            not any(path.exists() or path.is_symlink() for path in arm_slots),
        "arm_reload_never_touched_field_save_slots":
            arm_dir_valid and not bool(field_names & arm_names),
        "isolated_arm_sdmc_contains_only_two_valid_retreat_progress_slots":
            separate_game_directories
            and arm_names == {"arm-training-progress.a", "arm-training-progress.b"}
            and valid_two_retreat_progress_generations(progress_records),
    }
    result = {
        "kind": "stage405_real_nexium_arm_training_guest_audit",
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
