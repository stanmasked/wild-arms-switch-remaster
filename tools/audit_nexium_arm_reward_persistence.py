#!/usr/bin/env python3
"""Stage404: prove ARM rewards reload in a distinct NeXium cold-boot process."""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from audit_nexium_arm_guest import MAP_STATUS
from audit_nexium_field_journal import native_pixel, read_rgb

SCREENSHOTS = ("00_coldboot_field", "01_coldboot_reward_balance")
GREEN = MAP_STATUS
BALANCE_PIXELS = {
    "balance_EXP_E": (72, 667, True),
    "balance_EXP_8_not_1": (124, 667, True),
    "balance_GELLA_G": (163, 667, True),
    "balance_GELLA_first_digit_is_1": (241, 667, False),
    "balance_GELLA_second_digit_is_2": (254, 667, True),
}


def decode_reward_journal(path):
    data = Path(path).read_bytes()
    if len(data) != 32 or data[:4] != b"WAER":
        raise ValueError("invalid WAER journal size or magic")
    if data[4] != 1:
        raise ValueError("unsupported WAER journal version")
    if data[5:8] != b"\0\0\0" or data[24:28] != b"\0\0\0\0":
        raise ValueError("nonzero WAER reserved bytes")
    if zlib.crc32(data[:28]) != struct.unpack_from("<I", data, 28)[0]:
        raise ValueError("WAER checksum mismatch")
    generation = struct.unpack_from("<Q", data, 8)[0]
    if generation == 0:
        raise ValueError("zero WAER generation")
    exp, gella = struct.unpack_from("<II", data, 16)
    return {
        "generation": generation,
        "experience": exp,
        "gella": gella,
        "sha256": hashlib.sha256(data).hexdigest(),
        "raw": data,
    }


def audit_reward_persistence(screenshots, first_journal, after_restart_journal,
                             processes_path, data_root, report_path):
    screenshots = Path(screenshots)
    expected = {name + ".png" for name in SCREENSHOTS}
    actual = {path.name for path in screenshots.glob("*.png")}
    if actual != expected:
        raise ValueError(f"incorrect cold-boot screenshot set: {sorted(actual ^ expected)}")
    images = {name: read_rgb(screenshots / (name + ".png"))
              for name in SCREENSHOTS}
    field = images["00_coldboot_field"]
    balance = images["01_coldboot_reward_balance"]

    first = decode_reward_journal(first_journal)
    after = decode_reward_journal(after_restart_journal)
    process = json.loads(Path(processes_path).read_text(encoding="utf-8"))
    expected_keys = {
        "first_pid", "second_pid", "first_wait_completed",
        "second_wait_completed", "first_wait_status", "second_wait_status",
        "first_root", "second_root",
    }
    if set(process) != expected_keys:
        raise ValueError("unknown or missing cold-boot process evidence")
    root = str(Path(data_root).resolve())
    pids_valid = (
        type(process["first_pid"]) is int and process["first_pid"] > 0 and
        type(process["second_pid"]) is int and process["second_pid"] > 0 and
        process["first_pid"] != process["second_pid"]
    )
    waits_valid = (
        process["first_wait_completed"] is True and
        process["second_wait_completed"] is True and
        type(process["first_wait_status"]) is int and
        type(process["second_wait_status"]) is int and
        process["first_wait_status"] in (0, 137, 143) and
        process["second_wait_status"] in (0, 137, 143)
    )
    roots_valid = (
        isinstance(process["first_root"], str) and
        isinstance(process["second_root"], str) and
        Path(process["first_root"]).resolve() == Path(root) and
        Path(process["second_root"]).resolve() == Path(root)
    )

    game_dir = Path(data_root) / "sdmc" / "switch" / "wild_arms_field"
    names = {p.name for p in game_dir.iterdir()} if game_dir.is_dir() else set()
    try:
        committed_in_root = (game_dir / "arm-rewards.a").read_bytes()
    except OSError:
        committed_in_root = b""
    checks = {
        "two_distinct_ne_xium_processes_completed": pids_valid and waits_valid,
        "both_processes_used_the_same_isolated_sdmc_root": roots_valid,
        "first_victory_committed_generation_one_8_exp_12_gella":
            first["generation"] == 1 and first["experience"] == 8 and
            first["gella"] == 12,
        "cold_boot_read_preserved_exact_committed_journal_bytes":
            first["raw"] == after["raw"] == committed_in_root and
            after["generation"] == 1 and after["experience"] == 8 and
            after["gella"] == 12,
        "cold_boot_field_frame_is_visible":
            native_pixel(field, 0, 5) == GREEN,
        "cold_boot_arm_screen_shows_restored_8_exp_12_gella": all(
            (native_pixel(balance, x, y) == GREEN) == lit
            for _, (x, y, lit) in BALANCE_PIXELS.items()
        ),
        "arm_reward_journal_is_the_only_committed_slot":
            names == {"arm-rewards.a"},
        "field_and_regular_battle_save_slots_are_untouched":
            not any(name in names for name in (
                "field-save.a", "field-save.b", "field-save.tmp",
                "battle-progress.a", "battle-progress.b", "battle-progress.tmp",
            )),
    }

    payload = {
        "kind": "stage404_real_nexium_arm_reward_cold_boot",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journal": {
            "first_committed": {k: v for k, v in first.items() if k != "raw"},
            "after_restart": {k: v for k, v in after.items() if k != "raw"},
        },
        "processes": {
            "distinct_pids": pids_valid,
            "both_waited": waits_valid,
            "same_root": roots_valid,
        },
        "screenshot_sha256": {
            name: hashlib.sha256(
                (screenshots / (name + ".png")).read_bytes()
            ).hexdigest()
            for name in SCREENSHOTS
        },
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--first-journal", type=Path, required=True)
    parser.add_argument("--after-restart-journal", type=Path, required=True)
    parser.add_argument("--processes", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_reward_persistence(
            args.screenshots, args.first_journal, args.after_restart_journal,
            args.processes, args.data_root, args.report)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"ARM reward cold-boot audit rejected: {exc}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "Real ARM reward cold-boot persistence was not verified\n")
