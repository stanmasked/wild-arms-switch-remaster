#!/usr/bin/env python3
"""Stage368: prove alternating A/B CRC faults across 3 more genuine NeXium boots.

Audit consumes ONLY retained guest SDMC files, screenshots and key/PID logs.
No host-constructed state can substitute for executed emulated game evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal
from audit_nexium_battle_two_victories import victory, exactly

FRAMES = (
    "00_twentieth_fallback_three", "01_twentieth_fourth_victory",
    "02_twentieth_four_rewards", "03_twentyfirst_reload_four",
    "04_twentyfirst_after_retreat", "05_twentyfirst_retreat_panel",
    "06_twentysecond_fallback_four", "07_twentysecond_after_retreat",
    "08_twentysecond_repair_panel",
)
GREEN = (63, 191, 138)
GOLD = (245, 183, 66)
PANEL = (31, 45, 66)
PANEL_RECT = (*screen_point(680, 602), *screen_point(1250, 712))

# In-game 5x7 bitmap digits from include/field_battle_view.hpp, never OCR.
GLYPH = (
    (14, 17, 19, 21, 25, 17, 14),  # 0
    (4, 12, 4, 4, 4, 4, 14),       # 1
    (14, 17, 1, 2, 4, 8, 31),      # 2
    (30, 1, 1, 14, 1, 1, 30),      # 3
    (2, 6, 10, 18, 31, 2, 2),     # 4
    (31, 16, 16, 30, 1, 1, 30),   # 5
    (14, 16, 16, 30, 17, 17, 14), # 6
    (31, 1, 2, 4, 8, 8, 8),       # 7
    (14, 17, 17, 14, 17, 17, 14), # 8
    (14, 17, 17, 15, 1, 1, 14),   # 9
)


def same(a, b, rect):
    return ImageChops.difference(a.crop(rect), b.crop(rect)).getbbox() is None


def glyph(frame, x, y, digit, ink):
    bits = GLYPH[digit]
    return all(
        native_pixel(frame, x + 2 * c + 1, y + 2 * row + 1)
        == (ink if ((bits[row] >> (4-c)) & 1) else PANEL)
        for row in range(7) for c in range(5)
    )


def four_rewards(frame):
    # WINS 4, EXP 32, G 48 — exact digit masks, 175 distinct sample points.
    return (native_pixel(frame, 690, 612) == GOLD
            and glyph(frame, 776, 650, 4, GOLD)
            and glyph(frame, 1013, 623, 3, GREEN)
            and glyph(frame, 1026, 623, 2, GREEN)
            and glyph(frame, 1091, 623, 4, GREEN)
            and glyph(frame, 1104, 623, 8, GREEN))


def crc_only(original, damaged):
    a = Path(original).read_bytes()
    b = Path(damaged).read_bytes()
    if len(a) != 52 or len(b) != 52 or a[:4] != b"WABJ":
        raise ValueError("invalid CRC fault WABJ size/magic")
    if b[:48] != a[:48] or b[49:] != a[49:] or b[48] != (a[48] ^ 0x80):
        raise ValueError("fault must flip only outer WABJ CRC byte 48")
    try:
        read_journal(damaged)
    except ValueError:
        return
    raise ValueError("invalid test: damaged WABJ still passes CRC")


def check_provenance(old3, old17, old18_19, new, keys):
    paths = (old3, old17, old18_19, new)
    lines = [line for path in paths
             for line in Path(path).read_text(encoding="ascii").splitlines()]
    labels = ("fourteenth", "fifteenth", "sixteenth", "seventeenth",
              "eighteenth", "nineteenth", "twentieth", "twentyfirst",
              "twentysecond")
    if len(lines) != len(labels):
        raise ValueError("expected nine distinct, labelled process IDs")
    ids = []
    for label, line in zip(labels, lines):
        pair = line.split()
        if len(pair) != 2 or pair[0] != label or not pair[1].isdigit():
            raise ValueError("incorrect process provenance")
        ids.append(int(pair[1]))
    if min(ids) <= 0 or len(set(ids)) != 9:
        raise ValueError("NeXium guest process IDs reused")
    events = [line.split() for line in Path(keys).read_text(encoding="utf-8").splitlines()]
    expected = (
        [("twentieth", "x"), ("twentieth", "e")] +
        [("twentieth", "c")] * 7 +
        [("twentieth", "x"), ("twentyfirst", "x"),
         ("twentyfirst", "e"), ("twentyfirst", "x"),
         ("twentysecond", "x"), ("twentysecond", "e"),
         ("twentysecond", "x")]
    )
    if len(events) != len(expected):
        raise ValueError("unexpected key event count")
    for fields, (label, key) in zip(events, expected):
        if (len(fields) != 3 or fields[0] != label or
                fields[2] != key or not fields[1].endswith("Z")):
            raise ValueError("missing, reordered, or forged key edge")
    return ids


def audit_alternating(frames, original_field, three_win_panel,
                      base_gen5_a, base_gen4_b, damaged_a,
                      after20_a, after20_b, after21_a, after21_b,
                      damaged_b, after22_a, after22_b,
                      pids_three, pids_seventeen, pids_eighteen_nineteen,
                      pids_new, keys, report):
    root = Path(frames)
    expected = {name + ".png" for name in FRAMES}
    found = {path.name for path in root.glob("*.png")}
    if expected != found:
        raise ValueError(f"expected precisely nine guest screenshots: {sorted(expected ^ found)}")
    images = [read_rgb(root / (name + ".png")) for name in FRAMES]
    (fallback_three, fourth_win, four_panel, four_reload,
     ret_field, ret_panel, fallback_four, repaired_field, repaired_panel) = images
    raw_paths = {
        "base_gen5_a": base_gen5_a, "base_gen4_b": base_gen4_b,
        "after20_a": after20_a, "after20_b": after20_b,
        "after21_a": after21_a, "after21_b": after21_b,
        "after22_a": after22_a, "after22_b": after22_b,
    }
    saved = {k: Path(v).read_bytes() for k, v in raw_paths.items()}
    data = {k: read_journal(v) for k, v in raw_paths.items()}
    crc_only(base_gen5_a, damaged_a)
    crc_only(after21_b, damaged_b)
    process_ids = check_provenance(
        pids_three, pids_seventeen, pids_eighteen_nineteen, pids_new, keys)
    field = read_rgb(original_field)
    three = read_rgb(three_win_panel)

    checks = {
        "stage367_gen5_A_was_three_wins_two_retreats_24_36":
            exactly(data["base_gen5_a"], 5, 3, 3, 2, 24, 36),
        "stage367_gen4_B_was_three_wins_one_retreat_24_36":
            exactly(data["base_gen4_b"], 4, 1, 3, 1, 24, 36),
        "twentieth_guest_rolls_back_damaged_A_to_same_three_win_panel":
            same(fallback_three, three, GAME_ROI)
            and same(fallback_three, three, PANEL_RECT),
        "twentieth_guest_seven_real_A_edges_reach_fourth_victory":
            victory(fourth_win),
        "twentieth_guest_renders_four_wins_32EXP_48Gella":
            four_rewards(four_panel)
            and not same(four_panel, three, PANEL_RECT),
        "first_repair_of_A_records_new_victory_as_gen5_not_duplicate_retreat":
            exactly(data["after20_a"], 5, 1, 4, 1, 32, 48),
        "first_repair_preserves_old_gen4_B_bit_for_bit":
            saved["after20_b"] == saved["base_gen4_b"],
        "twentyfirst_guest_loads_same_four_win_panel_in_fresh_process":
            four_rewards(four_reload)
            and same(four_panel, four_reload, GAME_ROI)
            and same(four_panel, four_reload, PANEL_RECT),
        "twentyfirst_guest_retreat_returns_to_original_map":
            native_pixel(ret_field, 0, 5) == GREEN
            and same(field, ret_field, GAME_ROI)
            and same(field, ret_field, PANEL_RECT),
        "second_save_to_B_records_gen6_without_extra_rewards":
            exactly(data["after21_b"], 6, 3, 4, 2, 32, 48),
        "second_save_did_not_modify_repaired_gen5_A":
            saved["after21_a"] == saved["after20_a"],
        "twentysecond_guest_rolls_back_damaged_B_to_four_win_gen5_A":
            four_rewards(fallback_four)
            and same(four_panel, fallback_four, GAME_ROI)
            and same(four_panel, fallback_four, PANEL_RECT),
        "twentysecond_guest_returns_same_map_after_repair":
            native_pixel(repaired_field, 0, 5) == GREEN
            and same(field, repaired_field, GAME_ROI)
            and same(field, repaired_field, PANEL_RECT),
        "second_repair_preserves_A_and_restores_B_bit_for_bit":
            saved["after22_a"] == saved["after21_a"]
            and saved["after22_b"] == saved["after21_b"],
        "both_retreat_panels_match_after_B_recovery":
            same(ret_panel, repaired_panel, GAME_ROI)
            and same(ret_panel, repaired_panel, PANEL_RECT),
        "final_journal_has_four_wins_two_retreats_and_exactly_32_48":
            exactly(data["after22_a"], 5, 1, 4, 1, 32, 48)
            and exactly(data["after22_b"], 6, 3, 4, 2, 32, 48),
        "all_nine_guest_processes_distinct_and_key_edges_strict":
            len(set(process_ids)) == 9,
    }
    result = {
        "kind": "stage368_alternating_A_B_CRC_faults_and_fourth_earned_victory",
        "provenance": "three_actual_new_neXium_processes_same_stage365_367_SDMC",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journals": data,
        "sha256": {
            **{name: hashlib.sha256((root / (name + ".png")).read_bytes()).hexdigest()
               for name in FRAMES},
            **{name: hashlib.sha256(blob).hexdigest() for name, blob in saved.items()},
            "damaged_gen5_a": hashlib.sha256(Path(damaged_a).read_bytes()).hexdigest(),
            "damaged_gen6_b": hashlib.sha256(Path(damaged_b).read_bytes()).hexdigest(),
        },
    }
    out = Path(report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    args_list = (
        "frames original-field three-win-panel base-gen5-a base-gen4-b damaged-a "
        "after20-a after20-b after21-a after21-b damaged-b after22-a after22-b "
        "pids-three pids-seventeen pids-eighteen-nineteen pids-new keys report"
    ).split()
    for arg in args_list:
        p.add_argument("--" + arg, required=True)
    o = p.parse_args()
    try:
        data = audit_alternating(*(getattr(o, v.replace("-", "_")) for v in args_list))
    except (ValueError, TypeError, OSError) as ex:
        p.exit(2, f"Stage368 alternating WABJ CRC fault rejected: {ex}\n")
    print(json.dumps(data["checks"], sort_keys=True))
    if not data["all_checks_passed"]:
        p.exit(1, "Alternating two-slot guest SDMC verification failed\n")
