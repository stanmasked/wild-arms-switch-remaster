#!/usr/bin/env python3
"""Stage 367: real NeXium win after repaired newest CRC journal, then fresh reload.

Requires observed Xvfb guest PNGs, immutable WABJ journal copies, original
Stage366 evidence, independently checked input stream and six distinct PIDs.
ROM-free rewards in this probe are prototype values, not original PS1 values.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal
from audit_nexium_battle_two_victories import exactly, victory, reward_two

FRAMES = (
    "00_eighteenth_restored_gen3",
    "01_eighteenth_third_victory",
    "02_eighteenth_three_win_rewards",
    "03_nineteenth_reload_three_wins",
    "04_nineteenth_after_retreat",
)
GREEN = (63, 191, 138)
GOLD = (245, 183, 66)
PANEL = (31, 45, 66)
REWARD_TEXT_RECT = (*screen_point(958, 622), *screen_point(1130, 642))
PANEL_RECT = (*screen_point(680, 602), *screen_point(1250, 712))


def same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def reward_three(frame):
    # Observed 5x7 battle font rendered at x711 / x961 (2 native px/bit):
    # WINS 3 / EXP 24 / G 36. These sample locations distinguish 2/16/24.
    return (native_pixel(frame, 690, 612) == GOLD
            and native_pixel(frame, 778, 656) == GOLD
            and native_pixel(frame, 780, 656) == GOLD
            and native_pixel(frame, 782, 656) == GOLD
            and native_pixel(frame, 1017, 629) == PANEL
            and native_pixel(frame, 1019, 629) == GREEN
            and native_pixel(frame, 1026, 629) == GREEN
            and native_pixel(frame, 1093, 629) == GREEN
            and native_pixel(frame, 1108, 629) == GREEN
            and native_pixel(frame, 1106, 631) == PANEL)


def check_processes(prior_three_pids, prior_seventeenth_pid, two_new_pids):
    rows = (Path(prior_three_pids).read_text(encoding="ascii").splitlines()
            + Path(prior_seventeenth_pid).read_text(encoding="ascii").splitlines()
            + Path(two_new_pids).read_text(encoding="ascii").splitlines())
    labels = ("fourteenth", "fifteenth", "sixteenth", "seventeenth",
              "eighteenth", "nineteenth")
    if len(rows) != len(labels):
        raise ValueError("six labelled guest PIDs required")
    ids = []
    for expected, row in zip(labels, rows):
        parts = row.split()
        if len(parts) != 2 or parts[0] != expected or not parts[1].isdigit():
            raise ValueError(f"wrong PID provenance for {expected}")
        ids.append(int(parts[1]))
    if min(ids) <= 0 or len(set(ids)) != len(ids):
        raise ValueError("not six independent NeXium process PIDs")
    return ids


def check_key_edges(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if len(lines) != 13:
        raise ValueError("expected exactly thirteen distinct key press records")
    keys = []
    for line in lines:
        pieces = line.split()
        if len(pieces) != 2 or not pieces[0].endswith("Z"):
            raise ValueError("invalid key event audit record")
        keys.append(pieces[1])
    required = ["x", "e", *(["c"] * 7), "x", "x", "e", "x"]
    if keys != required:
        raise ValueError(f"invalid eighteen/nineteen guest key stream {keys}")
    return keys


def audit_post_repair(screens, original_field, recovered_two_win_panel,
                      repaired_gen3_a, retained_gen2_b,
                      third_win_a, third_win_b, final_a, final_b,
                      prior_three_pids, prior_seventeenth_pid, new_pids,
                      key_log, output):
    root = Path(screens)
    expected = {name + ".png" for name in FRAMES}
    found = {p.name for p in root.glob("*.png")}
    if found != expected:
        raise ValueError(f"guest screenshots missing/extra: {sorted(expected ^ found)}")
    frames = [read_rgb(root / (n + ".png")) for n in FRAMES]
    initial, win, earned, reloaded, returned = frames
    prior_panel = read_rgb(recovered_two_win_panel)
    original = read_rgb(original_field)
    sources = (repaired_gen3_a, retained_gen2_b, third_win_a,
               third_win_b, final_a, final_b)
    records = [read_journal(x) for x in sources]  # reject bad nested CRC first
    raw = [Path(x).read_bytes() for x in sources]
    pids = check_processes(prior_three_pids, prior_seventeenth_pid, new_pids)
    keys = check_key_edges(key_log)

    checks = {
        "stage366_repaired_gen3_A_starts_at_two_wins_16_24":
            exactly(records[0], 3, 3, 2, 1, 16, 24),
        "stage366_older_gen2_B_remains_a_valid_two_win_fallback":
            exactly(records[1], 2, 1, 2, 0, 16, 24),
        "eighteenth_fresh_guest_restores_two_wins_and_reward_digits":
            reward_two(initial)
            and same(initial, prior_panel, REWARD_TEXT_RECT),
        "seven_new_distinct_real_A_strikes_reach_third_victory":
            victory(win) and keys[2:9] == ["c"] * 7,
        "eighteenth_guest_ZL_renders_three_wins_24EXP_36Gella":
            reward_three(earned) and not same(initial, earned, REWARD_TEXT_RECT),
        "third_win_writes_generation_four_in_slot_B":
            exactly(records[3], 4, 1, 3, 1, 24, 36),
        "third_win_does_not_change_repaired_gen3_slot_A":
            raw[0] == raw[2] and records[0] == records[2],
        "nineteenth_process_restores_exact_three_win_panel_before_fighting":
            reward_three(reloaded)
            and same(earned, reloaded, GAME_ROI)
            and same(earned, reloaded, PANEL_RECT),
        "nineteenth_guest_retreat_returns_to_unchanged_field":
            native_pixel(returned, 0, 5) == GREEN
            and same(original, returned, GAME_ROI)
            and same(original, returned, PANEL_RECT),
        "nineteenth_retreat_writes_generation_five_in_A_without_reward":
            exactly(records[4], 5, 3, 3, 2, 24, 36),
        "generation_four_B_remains_bit_for_bit_unchanged_after_retreat":
            raw[3] == raw[5] and records[3] == records[5],
        "three_victories_preserve_cumulative_24EXP_36Gella_after_reboot":
            records[3]["experience"] == records[4]["experience"] == 24
            and records[3]["gella"] == records[4]["gella"] == 36
            and records[3]["wins"] == records[4]["wins"] == 3,
        "six_distinct_processes_and_exact_nonrepeated_key_edges":
            len(set(pids)) == 6 and len(keys) == 13,
    }
    report = {
        "kind": "real_neXium_post_CRC_repair_third_victory_and_fresh_reload",
        "provenance": "six_distinct_guests_one_sdmc_two_win_fault_then_third_win",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journals": dict(zip(
            ("repaired_gen3_a", "retained_gen2_b", "after_third_win_a",
             "after_third_win_b", "after_nineteenth_a", "after_nineteenth_b"),
            records)),
        "sha256": {
            **{n: hashlib.sha256((root / (n + ".png")).read_bytes()).hexdigest()
               for n in FRAMES},
            **{name: hashlib.sha256(blob).hexdigest()
               for name, blob in zip(
                  ("repaired_a", "retained_b", "third_win_a", "third_win_b",
                   "final_a", "final_b"), raw)},
            "keys": hashlib.sha256(Path(key_log).read_bytes()).hexdigest(),
            "new_pids": hashlib.sha256(Path(new_pids).read_bytes()).hexdigest(),
        },
    }
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("screens", "original-field", "recovered-two-win-panel",
                  "repaired-gen3-a", "retained-gen2-b",
                  "third-win-a", "third-win-b", "final-a", "final-b",
                  "prior-three-pids", "prior-seventeenth-pid", "new-pids",
                  "key-log", "output"):
        p.add_argument("--" + field, required=True)
    x = p.parse_args()
    try:
        audit = audit_post_repair(
            x.screens, x.original_field, x.recovered_two_win_panel,
            x.repaired_gen3_a, x.retained_gen2_b, x.third_win_a,
            x.third_win_b, x.final_a, x.final_b, x.prior_three_pids,
            x.prior_seventeenth_pid, x.new_pids, x.key_log, x.output)
    except (OSError, ValueError, TypeError) as exc:
        p.exit(2, f"Stage 367 post-CRC repair victory audit rejected: {exc}\n")
    print(json.dumps(audit["checks"], sort_keys=True))
    if not audit["all_checks_passed"]:
        p.exit(1, "Stage 367 real NeXium evidence failed\n")
