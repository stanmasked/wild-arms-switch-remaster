#!/usr/bin/env python3
"""Stage 360: verify real NeXium battle progress survives a fresh process.

Accept actual Xvfb frames and independently copied/committed WABJ journal
bytes. A host-synthetic fixture never proves a guest run.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel

NAMES = (
    "00_first_field", "01_first_zl_zero", "02_first_after_retreat",
    "03_reboot_zl_one", "04_reboot_zl_released",
    "05_reboot_after_second_retreat",
)
MAP = (63, 191, 138)
GOLD = (245, 183, 66)
WHITE = (246, 247, 252)
PANEL = (31, 45, 66)
SAFE_ROI = (260, 130, 1000, 580)
WABJ_BYTES = 52
WABR_BYTES = 36


def same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def read_journal(path):
    data = Path(path).read_bytes()
    if len(data) != WABJ_BYTES or data[:4] != b"WABJ":
        raise ValueError("invalid WABJ size or magic")
    generation = struct.unpack_from("<Q", data, 4)[0]
    if generation == 0:
        raise ValueError("zero generation")
    body = data[12:48]
    if body[:4] != b"WABR" or body[4] != 1:
        raise ValueError("invalid WABR magic/version")
    if body[6:8] != b"\0\0" or body[28:32] != b"\0\0\0\0":
        raise ValueError("nonzero reserved bytes")
    if zlib.crc32(body[:32]) != struct.unpack_from("<I", body, 32)[0]:
        raise ValueError("inner WABR checksum mismatch")
    if zlib.crc32(data[:48]) != struct.unpack_from("<I", data, 48)[0]:
        raise ValueError("outer WABJ checksum mismatch")
    outcome = body[5]
    wins, losses, exits, exp, gella = struct.unpack_from("<IIIII", body, 8)
    if (outcome not in (0, 1, 2, 3) or
        (outcome == 0 and (wins or losses or exits)) or
        (outcome == 1 and not wins) or
        (outcome == 2 and not losses) or
        (outcome == 3 and not exits) or
        (not wins and (exp or gella))):
        raise ValueError("invalid battle journal semantic values")
    return {
        "generation": generation, "outcome": outcome,
        "wins": wins, "losses": losses, "retreats": exits,
        "experience": exp, "gella": gella,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def audit_persistence(directory, first_journal, committed_a, committed_b,
                      output):
    directory = Path(directory)
    found = {p.name for p in directory.glob("*.png")}
    expected = {n + ".png" for n in NAMES}
    if found != expected:
        raise ValueError(f"incorrect six screenshot set: {sorted(found ^ expected)}")
    s = {n: read_rgb(directory / (n + ".png")) for n in NAMES}
    before, zero, closed, reloaded, released, closed_again = (
        s[n] for n in NAMES
    )
    initial = read_journal(first_journal)
    after_a = read_journal(committed_a)
    after_b = read_journal(committed_b)
    panel_box = (*screen_point(680, 602), *screen_point(1250, 712))
    checks = {
        "initial_guest_field_has_no_panel":
            native_pixel(before, 0, 5) == MAP
            and native_pixel(before, 690, 612) != GOLD,
        "first_guest_ZL_indicates_zero_retreat":
            native_pixel(zero, 690, 612) == GOLD
            and native_pixel(zero, 789, 681) == WHITE
            and native_pixel(zero, 793, 681) == PANEL
            and same(before, zero, SAFE_ROI),
        "first_guest_B_return_same_map":
            native_pixel(closed, 0, 5) == MAP
            and same(before, closed, GAME_ROI)
            and same(before, closed, panel_box),
        "first_guest_wrote_only_valid_generation_one":
            initial["generation"] == 1 and initial["outcome"] == 3
            and initial["retreats"] == 1
            and initial["wins"] == initial["losses"] == 0
            and initial["experience"] == initial["gella"] == 0,
        "second_fresh_guest_reloads_one_retreat_into_ZL":
            native_pixel(reloaded, 690, 612) == GOLD
            and native_pixel(reloaded, 789, 681) == PANEL
            and native_pixel(reloaded, 793, 681) == WHITE
            and native_pixel(reloaded, 923, 679) == WHITE
            and same(before, reloaded, SAFE_ROI),
        "second_guest_ZL_release_restores_same_map":
            same(before, released, GAME_ROI)
            and same(before, released, panel_box),
        "second_guest_B_return_keeps_identical_map":
            same(before, closed_again, GAME_ROI)
            and same(before, closed_again, panel_box),
        "second_guest_commits_next_generation_with_unmodified_prior":
            after_a == initial and after_b["generation"] == 2
            and after_b["outcome"] == 3 and after_b["retreats"] == 2
            and after_b["wins"] == after_b["losses"] == 0
            and after_b["experience"] == after_b["gella"] == 0,
    }
    report = {
        "kind": "real_two_process_nexium_battle_sdmc_recovery",
        "provenance": "two_distinct_guest_pids_same_isolated_SDMC_root",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "journals": {"first_copy": initial, "committed_a": after_a,
                     "committed_b": after_b},
        "sha256": {
            name: hashlib.sha256((directory / (name + ".png")).read_bytes()).hexdigest()
            for name in NAMES
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--screenshots", type=Path, required=True)
    p.add_argument("--first-journal", type=Path, required=True)
    p.add_argument("--committed-a", type=Path, required=True)
    p.add_argument("--committed-b", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    opts = p.parse_args()
    try:
        result = audit_persistence(opts.screenshots, opts.first_journal,
                                   opts.committed_a, opts.committed_b,
                                   opts.report)
    except (OSError, ValueError, TypeError) as ex:
        p.exit(2, f"Battle journal guest persistence audit rejected: {ex}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1, "Real two-process battle persistence was not verified\n")
