#!/usr/bin/env python3
"""Stage369: verify BOTH corrupted WABJ slots fail closed in two real NeXium boots.

Unlike single-slot fallback, simultaneous invalid A/B must NOT restore a
previous value, MUST NOT replace either invalid slot on B-close, and may
only change volatile in-process retreat statistics. Two independent guests
must restart at zero. This does not claim recovered lost rewards.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal
from audit_nexium_battle_alternating_faults import GLYPH, GREEN, GOLD, PANEL

NAMES = (
    "00_twentythird_zero_after_corruption",
    "01_twentythird_after_retreat",
    "02_twentythird_volatile_retreat",
    "03_twentyfourth_zero_after_reboot",
    "04_twentyfourth_after_retreat",
    "05_twentyfourth_volatile_retreat",
)
PANEL_RECT = (*screen_point(680, 602), *screen_point(1250, 712))


def same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def digit(frame, x, y, n, color, sample_y=1):
    glyph = GLYPH[n]
    return all(
        native_pixel(frame, x+2*col+1, y+2*row+sample_y)
        == (color if (glyph[row] >> (4-col)) & 1 else PANEL)
        for row in range(7) for col in range(5)
    )


def zero_rewards(frame):
    # x = initial + glyph index * 13, integer glyphs 5x7 at scale 2.
    # WINS 0; EXP 0  G 0 on deliberately held ZL panel.
    return (native_pixel(frame, 690, 612) == GOLD
            and digit(frame, 776, 650, 0, GOLD)
            and digit(frame, 1013, 623, 0, GREEN)
            and digit(frame, 1078, 623, 0, GREEN)
            and digit(frame, 789, 677, 0, (246, 247, 252), sample_y=0))


def one_volatile_retreat(frame):
    return (not zero_rewards(frame)
            and digit(frame, 776, 650, 0, GOLD)
            and digit(frame, 1013, 623, 0, GREEN)
            and digit(frame, 1078, 623, 0, GREEN)
            and digit(frame, 789, 677, 1, (246, 247, 252), sample_y=0))


def single_crc_flip(original, corrupted):
    a = Path(original).read_bytes()
    b = Path(corrupted).read_bytes()
    if len(a) != 52 or len(b) != 52 or a[:4] != b"WABJ":
        raise ValueError("invalid WABJ source/fault")
    if a[:48] != b[:48] or a[49:] != b[49:] or (a[48] ^ 0x80) != b[48]:
        raise ValueError("fault changed more than single CRC byte 48")
    read_journal(original)  # must be a genuinely valid original
    try:
        read_journal(corrupted)
    except ValueError:
        return
    raise ValueError("invalid slot still accepted after CRC fault")


def distinct_guests(existing, new):
    old_lines = Path(existing).read_text(encoding="ascii").splitlines()
    new_lines = Path(new).read_text(encoding="ascii").splitlines()
    old_labels = ("twentieth", "twentyfirst", "twentysecond")
    new_labels = ("twentythird", "twentyfourth")
    if len(old_lines) != 3 or len(new_lines) != 2:
        raise ValueError("expected 3 prior and 2 new labelled PIDs")
    ids = []
    for line, label in zip(old_lines+new_lines, old_labels+new_labels):
        fields = line.split()
        if len(fields) != 2 or fields[0] != label or not fields[1].isdigit():
            raise ValueError("invalid guest PID provenance")
        ids.append(int(fields[1]))
    if min(ids) <= 0 or len(set(ids)) != len(ids):
        raise ValueError("NeXium guest PID not unique")
    return ids


def check_edges(path):
    lines = Path(path).read_text(encoding="ascii").splitlines()
    expected = [
        ("twentythird", "x"), ("twentythird", "e"), ("twentythird", "x"),
        ("twentyfourth", "x"), ("twentyfourth", "e"), ("twentyfourth", "x"),
    ]
    if len(lines) != len(expected):
        raise ValueError("six key presses required, no A attacks")
    for line, expected_pair in zip(lines, expected):
        bits = line.split()
        if (len(bits) != 3 or (bits[0], bits[2]) != expected_pair or
                not bits[1].endswith("Z")):
            raise ValueError("unexpected/forged controller event")


def audit_both_corrupt(screens, original_field,
                       intact_a, intact_b, corrupt_a, corrupt_b,
                       after23_a, after23_b, after24_a, after24_b,
                       old_pids, new_pids, key_log, report):
    path = Path(screens)
    expected = {x+".png" for x in NAMES}
    found = {p.name for p in path.glob("*.png")}
    if found != expected:
        raise ValueError(f"missing/extra PNGs: {sorted(expected ^ found)}")
    frames = [read_rgb(path/(x+".png")) for x in NAMES]
    initial, ret23, stats23, reboot, ret24, stats24 = frames
    base = read_rgb(original_field)

    single_crc_flip(intact_a, corrupt_a)
    single_crc_flip(intact_b, corrupt_b)
    original_files = [Path(p).read_bytes() for p in (intact_a, intact_b)]
    damaged = [Path(p).read_bytes() for p in (corrupt_a, corrupt_b)]
    copies = [Path(p).read_bytes() for p in
              (after23_a, after23_b, after24_a, after24_b)]
    ids = distinct_guests(old_pids, new_pids)
    check_edges(key_log)
    checks = {
        "two_distinct_valid_pre_fault_journals":
            original_files[0] != original_files[1]
            and read_journal(intact_a)["generation"] == 5
            and read_journal(intact_b)["generation"] == 6,
        "both_newest_and_backup_CRC_bytes_were_independently_corrupted":
            damaged[0] != original_files[0] and damaged[1] != original_files[1],
        "twentythird_boot_did_not_show_unverifiable_stored_rewards":
            zero_rewards(initial),
        "twentythird_B_retreat_returns_original_field":
            native_pixel(ret23, 0, 5) == GREEN
            and same(base, ret23, GAME_ROI)
            and same(base, ret23, PANEL_RECT),
        "twentythird_retreat_only_updates_volatile_in_memory_history":
            one_volatile_retreat(stats23),
        "twentythird_failed_save_did_not_rewrite_either_corrupt_slot":
            copies[0] == damaged[0] and copies[1] == damaged[1],
        "twentyfourth_guest_reboots_again_with_zero_rewards":
            zero_rewards(reboot)
            and same(initial, reboot, GAME_ROI)
            and same(initial, reboot, PANEL_RECT),
        "twentyfourth_retreat_returns_original_field":
            native_pixel(ret24, 0, 5) == GREEN
            and same(base, ret24, GAME_ROI)
            and same(base, ret24, PANEL_RECT),
        "twentyfourth_volatile_panel_matches_first_volatile_retreat":
            one_volatile_retreat(stats24)
            and same(stats23, stats24, GAME_ROI)
            and same(stats23, stats24, PANEL_RECT),
        "twentyfourth_failed_save_kept_both_corrupt_slots_unchanged":
            copies[2] == damaged[0] and copies[3] == damaged[1],
        "no_earnings_or_fabricated_victory_after_double_CRC_failure":
            all(digit(p, 776, 650, 0, GOLD)
                    and digit(p, 1013, 623, 0, GREEN)
                    and digit(p, 1078, 623, 0, GREEN)
                    for p in (initial, stats23, reboot, stats24)),
        "five_relevant_NeXium_processes_are_distinct_and_no_attacks_sent":
            len(set(ids)) == 5,
    }
    files = dict(zip(
        ("original_a", "original_b", "damaged_a", "damaged_b",
         "after_23_a", "after_23_b", "after_24_a", "after_24_b"),
        original_files+damaged+copies))
    result = {
        "kind": "two_corrupt_wabj_slots_fail_closed_without_automatic_overwrite",
        "provenance": "two_independent_real_guest_processes_after_stage368",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "sha256": {
            **{name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
            **{name: hashlib.sha256((path/(name+".png")).read_bytes()).hexdigest()
               for name in NAMES},
        },
    }
    out = Path(report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, sort_keys=True, indent=2)+"\n",
                   encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    names = ("screens original-field intact-a intact-b corrupt-a corrupt-b "
             "after23-a after23-b after24-a after24-b old-pids new-pids "
             "key-log report").split()
    for name in names:
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    try:
        result = audit_both_corrupt(
            *(getattr(a, name.replace("-", "_")) for name in names))
    except (ValueError, OSError, TypeError) as e:
        p.exit(2, f"Stage369 both-corrupt audit rejected: {e}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1, "Stage369 did not prove safe failure on double CRC damage\n")
