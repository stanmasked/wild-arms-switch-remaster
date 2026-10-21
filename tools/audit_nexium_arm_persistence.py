#!/usr/bin/env python3
"""Stage405: prove a fifth real NeXium process restores ARM rewards from SDMC.

The screenshot must be captured from the actual guest workflow. Synthetic
screenshots and journal records are only the separately labelled unit-test
oracle; they are never evidence that NeXium ran.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_cold_boot import valid_terminated
from audit_nexium_arm_guest import battle_slots, GOLD, read_arm_progress_slot
from audit_nexium_arm_victory import (
    balance_pixels, EXP_START, EXP_8_MIDDLE, GELLA_1, GELLA_2,
)
from audit_nexium_field_journal import native_pixel, read_rgb

RETREATS_ONE = (70 + 12 * 13 + 4, 687)


def audit_persistence(shot, processes_path, victory_process_path, arm_root, report):
    shot = Path(shot)
    frame = read_rgb(shot)
    processes = json.loads(Path(processes_path).read_text(encoding="utf-8"))
    victory = json.loads(Path(victory_process_path).read_text(encoding="utf-8"))
    required = {
        "victoryrestart_pid", "victoryrestart_wait_status",
        "victoryrestart_force_killed", "victoryrestart_wait_completed",
    }
    if set(processes) != required:
        raise ValueError("missing/unexpected fifth-process evidence")
    victory_required = {
        "victory_pid", "victory_wait_status",
        "victory_force_killed", "victory_wait_completed",
    }
    if set(victory) != victory_required:
        raise ValueError("missing/unexpected fourth-process evidence")

    root = Path(arm_root)
    directory = root / "sdmc" / "switch" / "wild_arms_field"
    rooted = directory.is_dir() and not directory.is_symlink()
    names = {p.name for p in directory.iterdir()} if rooted else set()
    arm_a = directory / "arm-training-progress.a"
    arm_b = directory / "arm-training-progress.b"
    if not rooted or not arm_a.is_file() or arm_a.is_symlink() or not arm_b.is_file() or arm_b.is_symlink():
        raise ValueError("both committed ARM progress slots must exist")
    older = read_arm_progress_slot(arm_a)
    latest = read_arm_progress_slot(arm_b)

    pids = (victory.get("victory_pid"), processes.get("victoryrestart_pid"))
    checks = {
        "fifth_guest_is_a_distinct_terminated_ne_xium_process":
            all(type(pid) is int and pid > 0 for pid in pids)
            and pids[0] != pids[1]
            and victory.get("victory_wait_completed") is True
            and processes.get("victoryrestart_wait_completed") is True
            and valid_terminated(victory, "victory")
            and valid_terminated(processes, "victoryrestart"),
        "real_cold_boot_frame_shows_exact_persisted_exp_and_gella":
            balance_pixels(frame)
            and all(native_pixel(frame, *point) == (63, 191, 138)
                    for point in (EXP_START, EXP_8_MIDDLE, GELLA_1, GELLA_2)),
        "real_cold_boot_frame_shows_persisted_retreat_history":
            native_pixel(frame, *RETREATS_ONE) == GOLD,
        "older_slot_is_the_confirmed_victory_generation":
            older["generation"] == 1 and older["last"] == 1
            and older["wins"] == 1 and older["losses"] == 0
            and older["retreats"] == 0
            and older["experience"] == 8 and older["gella"] == 12,
        "latest_slot_preserves_reward_after_retreat":
            latest["generation"] == 2 and latest["last"] == 3
            and latest["wins"] == 1 and latest["losses"] == 0
            and latest["retreats"] == 1
            and latest["experience"] == 8 and latest["gella"] == 12,
        "only_two_arm_progress_slots_exist_in_dedicated_namespace":
            names == {"arm-training-progress.a", "arm-training-progress.b"}
            and not any(slot.exists() for slot in battle_slots(root))
            and not any((directory / name).exists() for name in (
                "field-save.a", "field-save.b", "field-save.tmp",
            )),
    }
    payload = {
        "kind": "stage405_real_fifth_ne_xium_arm_reward_cold_boot",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "process_ids": {"fourth": pids[0], "fifth": pids[1]},
        "journal": {"older": older, "latest": latest},
        "sha256": {"screenshot": hashlib.sha256(shot.read_bytes()).hexdigest()},
        "scope": "experimental_asset_free_ARM_rewards_only_separate_from_field_and_regular_battle_saves",
    }
    target = Path(report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return payload


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shot", type=Path, required=True)
    p.add_argument("--processes", type=Path, required=True)
    p.add_argument("--victory-process", type=Path, required=True)
    p.add_argument("--arm-root", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    try:
        result = audit_persistence(args.shot, args.processes,
            args.victory_process, args.arm_root, args.report)
    except (OSError, ValueError, TypeError, KeyError) as err:
        p.exit(2, f"NeXium ARM persistence auditor rejected: {err}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1, "Actual NeXium ARM reward cold-boot proof failed\n")
