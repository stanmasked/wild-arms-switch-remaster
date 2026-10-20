#!/usr/bin/env python3
"""Stage 365: independently audit two wins over three actual NeXium guest boots.

Strict Xvfb screenshots + immutable copies of guest SDMC WABJ records.
Synthetic fixture tests do not constitute proof of real guest execution.
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
    "00_first_manual", "01_first_victory", "02_first_rewards",
    "03_second_reload", "04_second_victory", "05_second_rewards",
    "06_third_reload", "07_third_retreat",
)
GREEN = (63, 191, 138)
GOLD = (245, 183, 66)
PANEL = (31, 45, 66)
DARK = (12, 19, 31)
PANEL_BOX = (*screen_point(680, 602), *screen_point(1250, 712))


def same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def victory(frame):
    return (native_pixel(frame, 324, 297) == GREEN
            and native_pixel(frame, 500, 296) == GREEN
            and native_pixel(frame, 500, 298) == DARK
            and native_pixel(frame, 700, 249) == DARK)


def reward_one(frame):
    return (native_pixel(frame, 690, 612) == GOLD
            and native_pixel(frame, 780, 656) == GOLD
            and native_pixel(frame, 782, 656) == PANEL
            and native_pixel(frame, 1015, 629) == GREEN
            and native_pixel(frame, 1080, 625) == GREEN
            and native_pixel(frame, 1091, 635) == GREEN)


def reward_two(frame):
    # Digits changed from WINS 1, EXP 8, G 12 to WINS 2, EXP 16, G 24.
    return (native_pixel(frame, 690, 612) == GOLD
            and native_pixel(frame, 780, 656) == PANEL
            and native_pixel(frame, 782, 656) == GOLD
            and native_pixel(frame, 1015, 629) == PANEL
            and native_pixel(frame, 1017, 629) == GREEN
            and native_pixel(frame, 1027, 629) == GREEN
            and native_pixel(frame, 1093, 623) == GREEN
            and native_pixel(frame, 1105, 631) == GREEN)


def exactly(record, generation, outcome, wins, retreats, experience, gella):
    return (record["generation"] == generation
            and record["outcome"] == outcome
            and record["wins"] == wins and record["losses"] == 0
            and record["retreats"] == retreats
            and record["experience"] == experience
            and record["gella"] == gella)


def read_pids(path):
    rows = Path(path).read_text(encoding="ascii").splitlines()
    labels = ("fourteenth", "fifteenth", "sixteenth")
    if len(rows) != len(labels):
        raise ValueError("expected three guest PIDs")
    ids = []
    for row, label in zip(rows, labels):
        bits = row.split()
        if len(bits) != 2 or bits[0] != label or not bits[1].isdigit():
            raise ValueError("invalid labelled NeXium PID")
        pid = int(bits[1])
        if pid <= 0:
            raise ValueError("invalid guest PID")
        ids.append(pid)
    if len(set(ids)) != len(labels):
        raise ValueError("duplicate NeXium guest PIDs")
    return ids


def audit_two_victories(screenshots, first_a, second_a, second_b,
                        final_a, final_b, pids, report):
    root = Path(screenshots)
    actual = {p.name for p in root.glob("*.png")}
    expected = {name + ".png" for name in NAMES}
    if actual != expected:
        raise ValueError(f"missing/extra guest screenshots: {sorted(actual ^ expected)}")
    images = [read_rgb(root / (name + ".png")) for name in NAMES]
    before, victory1, rewards1, reload1, victory2, rewards2, reload2, retreat = images
    paths = [Path(p) for p in (first_a, second_a, second_b, final_a, final_b)]
    raw = [p.read_bytes() for p in paths]
    journal = [read_journal(p) for p in paths]  # independent nested CRC32 verification
    guest_pids = read_pids(pids)
    checks = {
        "first_guest_starts_on_original_uncovered_field":
            native_pixel(before, 0, 5) == GREEN
            and native_pixel(before, 690, 612) != GOLD,
        "seven_first_guest_A_attacks_reached_actual_victory": victory(victory1),
        "first_victory_committed_gen1_eight_EXP_twelve_Gella":
            exactly(journal[0], 1, 1, 1, 0, 8, 12),
        "first_guest_shows_one_win_eight_EXP_twelve_Gella": reward_one(rewards1),
        "second_fresh_guest_restores_first_rewards_before_combat":
            same(rewards1, reload1, GAME_ROI)
            and same(rewards1, reload1, PANEL_BOX) and reward_one(reload1),
        "seven_second_guest_A_attacks_reached_actual_victory": victory(victory2),
        "second_guest_renders_two_wins_sixteen_EXP_twentyfour_Gella":
            reward_two(rewards2) and not same(rewards1, rewards2, PANEL_BOX),
        "second_victory_committed_gen2_sixteen_EXP_twentyfour_Gella":
            exactly(journal[2], 2, 1, 2, 0, 16, 24),
        "first_generation_slot_A_unchanged_after_second_win":
            raw[0] == raw[1] and journal[0] == journal[1],
        "third_fresh_guest_restores_two_wins_before_combat":
            same(rewards2, reload2, GAME_ROI)
            and same(rewards2, reload2, PANEL_BOX) and reward_two(reload2),
        "third_guest_retreat_restores_original_field":
            native_pixel(retreat, 0, 5) == GREEN
            and same(before, retreat, GAME_ROI)
            and same(before, retreat, PANEL_BOX),
        "third_guest_retreat_commits_gen3_without_extra_rewards":
            exactly(journal[3], 3, 3, 2, 1, 16, 24),
        "second_generation_slot_B_unchanged_after_third_guest":
            raw[2] == raw[4] and journal[2] == journal[4],
        "guest_processes_are_distinct": len(set(guest_pids)) == 3,
    }
    result = {
        "kind": "three_real_NeXium_guests_cumulative_two_victories",
        "provenance": "three_distinct_guest_processes_one_isolated_SDMC",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journals": dict(zip(("first_a", "second_a", "second_b", "final_a", "final_b"), journal)),
        "sha256": {
            **{name: hashlib.sha256((root / (name + ".png")).read_bytes()).hexdigest()
               for name in NAMES},
            **{name: hashlib.sha256(data).hexdigest() for name, data in zip(
                ("first_a", "second_a", "second_b", "final_a", "final_b"), raw)},
            "guest_pids": hashlib.sha256(Path(pids).read_bytes()).hexdigest(),
        },
    }
    dest = Path(report)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", required=True)
    parser.add_argument("--first-a", required=True)
    parser.add_argument("--second-a", required=True)
    parser.add_argument("--second-b", required=True)
    parser.add_argument("--final-a", required=True)
    parser.add_argument("--final-b", required=True)
    parser.add_argument("--pids", required=True)
    parser.add_argument("--report", required=True)
    a = parser.parse_args()
    try:
        result = audit_two_victories(a.screenshots, a.first_a, a.second_a,
                                     a.second_b, a.final_a, a.final_b,
                                     a.pids, a.report)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Stage 365 NeXium audit rejected: {error}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "Two real guest victories were not proven\n")
