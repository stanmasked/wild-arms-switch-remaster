#!/usr/bin/env python3
"""Stage 366: newest CRC-damaged 2-win WABJ fallback and repair in guest 17.

Read-only audit: accepts real Xvfb frames, separate immutable guest SDMC
journal copies, and process identity. No synthetic fixture is guest proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal
from audit_nexium_battle_two_victories import exactly, reward_two

FRAMES = ("00_crc_fallback_rewards", "01_after_repaired_retreat")
MAP = (63, 191, 138)
PANEL_RECT = (*screen_point(680, 602), *screen_point(1250, 712))


def same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def distinct_processes(previous, new):
    old = Path(previous).read_text(encoding="ascii").splitlines()
    new_line = Path(new).read_text(encoding="ascii").strip()
    names = ("fourteenth", "fifteenth", "sixteenth")
    if len(old) != 3:
        raise ValueError("stage365 must identify three prior guests")
    ids = []
    for name, line in zip(names, old):
        parts = line.split()
        if len(parts) != 2 or parts[0] != name or not parts[1].isdigit():
            raise ValueError("invalid previous guest provenance")
        ids.append(int(parts[1]))
    parts = new_line.split()
    if len(parts) != 2 or parts[0] != "seventeenth" or not parts[1].isdigit():
        raise ValueError("seventeenth guest PID is absent or forged")
    ids.append(int(parts[1]))
    if min(ids) <= 0 or len(set(ids)) != 4:
        raise ValueError("NeXium guest PID reuse")
    return ids


def audit_fallback(frames, original_field, known_second_win_panel,
                   valid_latest_a, valid_fallback_b, corrupt_latest_a,
                   repaired_a, unchanged_b, previous_pids, seventeenth_pid,
                   report):
    folder = Path(frames)
    found = {p.name for p in folder.glob("*.png")}
    expected = {s + ".png" for s in FRAMES}
    if found != expected:
        raise ValueError(f"expected exactly two observed guest PNGs: {sorted(found ^ expected)}")
    files = {
        "latest_before": Path(valid_latest_a),
        "fallback_before": Path(valid_fallback_b),
        "corrupt": Path(corrupt_latest_a),
        "latest_after": Path(repaired_a),
        "fallback_after": Path(unchanged_b),
    }
    raw = {name: path.read_bytes() for name, path in files.items()}
    before_a, before_b, corrupt, after_a, after_b = (
        raw[n] for n in ("latest_before", "fallback_before", "corrupt",
                        "latest_after", "fallback_after")
    )
    if len(before_a) != 52 or len(corrupt) != 52:
        raise ValueError("newest journal must be exactly 52 bytes")
    if (len(before_b) != 52 or len(after_a) != 52 or len(after_b) != 52):
        raise ValueError("incorrect WABJ file size")
    if (corrupt[:48] != before_a[:48] or corrupt[49:] != before_a[49:]
            or corrupt[48] != (before_a[48] ^ 0x80)):
        raise ValueError("corruption must alter ONLY byte 48 of newest A CRC")
    try:
        read_journal(corrupt_latest_a)
    except ValueError:
        pass
    else:
        raise ValueError("damaged newest A was accepted unexpectedly")
    parsed = {
        "latest_before": read_journal(valid_latest_a),
        "fallback_before": read_journal(valid_fallback_b),
        "latest_after": read_journal(repaired_a),
        "fallback_after": read_journal(unchanged_b),
    }
    pids = distinct_processes(previous_pids, seventeenth_pid)
    initial_map = read_rgb(original_field)
    known_panel = read_rgb(known_second_win_panel)
    fallback_frame = read_rgb(folder / (FRAMES[0] + ".png"))
    repaired_field = read_rgb(folder / (FRAMES[1] + ".png"))

    checks = {
        "original_gen3_A_has_two_wins_one_retreat_and_16_24":
            exactly(parsed["latest_before"], 3, 3, 2, 1, 16, 24),
        "older_gen2_B_has_two_wins_zero_retreat_and_16_24":
            exactly(parsed["fallback_before"], 2, 1, 2, 0, 16, 24),
        "fallback_guest_ZL_restored_previous_wins_EXP_and_Gella":
            same(known_panel, fallback_frame, GAME_ROI)
            and same(known_panel, fallback_frame, PANEL_RECT)
            and reward_two(fallback_frame),
        "damaged_slot_was_repaired_to_gen3_only_after_retreat":
            exactly(parsed["latest_after"], 3, 3, 2, 1, 16, 24),
        "no_extra_reward_or_double_credit_after_repaired_retreat":
            parsed["latest_after"]["experience"] == 16
            and parsed["latest_after"]["gella"] == 24
            and parsed["latest_after"]["wins"] == 2
            and parsed["latest_after"]["retreats"] == 1,
        "gen3_A_repair_is_byte_equal_to_original_valid_gen3_A":
            after_a == before_a,
        "prior_gen2_B_was_never_modified":
            after_b == before_b
            and parsed["fallback_after"] == parsed["fallback_before"],
        "seventeenth_guest_returned_exact_original_field":
            native_pixel(repaired_field, 0, 5) == MAP
            and same(initial_map, repaired_field, GAME_ROI)
            and same(initial_map, repaired_field, PANEL_RECT),
        "four_independent_guest_processes": len(set(pids)) == 4,
    }
    result = {
        "kind": "stage366_newest_WABJ_crc_recovery_preserves_two_wins_and_16_24",
        "provenance": "seventeenth_real_guest_same_SDMC_after_three_verified_stage365_guests",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journals": parsed,
        "sha256": {
            **{name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
            **{name: hashlib.sha256((folder / (name + ".png")).read_bytes()).hexdigest()
               for name in FRAMES},
            "prior_guest_pids": hashlib.sha256(Path(previous_pids).read_bytes()).hexdigest(),
            "new_guest_pid": hashlib.sha256(Path(seventeenth_pid).read_bytes()).hexdigest(),
        },
    }
    dest = Path(report)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("frames", "original-field", "known-second-win-panel",
                 "valid-latest-a", "valid-fallback-b", "corrupt-latest-a",
                 "repaired-a", "unchanged-b", "previous-pids", "seventeenth-pid",
                 "report"):
        p.add_argument("--" + flag, required=True)
    args = p.parse_args()
    try:
        result = audit_fallback(
            args.frames, args.original_field, args.known_second_win_panel,
            args.valid_latest_a, args.valid_fallback_b,
            args.corrupt_latest_a, args.repaired_a, args.unchanged_b,
            args.previous_pids, args.seventeenth_pid, args.report)
    except (OSError, ValueError, TypeError) as exc:
        p.exit(2, f"Stage366 CRC fallback rejected: {exc}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1, "Real guest fallback to two victory rewards was not verified\n")
