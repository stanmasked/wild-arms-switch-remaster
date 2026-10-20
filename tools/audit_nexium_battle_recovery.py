#!/usr/bin/env python3
"""Stage 361: evidence for recovery from corrupted newest NeXium battle journal.

An 11th newly booted guest must load previous valid A after B CRC damage,
display one retreat, then commit the repaired B generation 2. This is
an independent *real guest evidence* validator, not a save emulator.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal

NAMES = ("00_corrupt_reboot_zl_one", "01_after_repaired_retreat")
MAP = (63, 191, 138)
GOLD = (245, 183, 66)
WHITE = (246, 247, 252)
PANEL = (31, 45, 66)


def _same(a, b, roi):
    return ImageChops.difference(a.crop(roi), b.crop(roi)).getbbox() is None


def audit_recovery(screens, original_field, original_a, original_b,
                   corrupted_b, repaired_a, repaired_b, output):
    screens = Path(screens)
    found = {p.name for p in screens.glob("*.png")}
    expected = {n + ".png" for n in NAMES}
    if found != expected:
        raise ValueError(f"11th guest expects two screenshots: {sorted(found ^ expected)}")

    valid_a = Path(original_a).read_bytes()
    valid_b = Path(original_b).read_bytes()
    damaged = Path(corrupted_b).read_bytes()
    after_a = Path(repaired_a).read_bytes()
    after_b = Path(repaired_b).read_bytes()
    if len(valid_b) != 52 or len(damaged) != 52:
        raise ValueError("invalid copy sizes")
    if damaged[:48] != valid_b[:48] or damaged[49:] != valid_b[49:] or (
        damaged[48] != (valid_b[48] ^ 0x80)
    ):
        raise ValueError("test must corrupt ONLY outer CRC byte 48")
    try:
        read_journal(corrupted_b)
    except ValueError:
        pass
    else:
        raise ValueError("corrupted newest B was still accepted")
    a = read_journal(original_a)
    b = read_journal(original_b)
    recovered_a = read_journal(repaired_a)
    recovered_b = read_journal(repaired_b)
    field = read_rgb(original_field)
    reloaded = read_rgb(screens / (NAMES[0] + ".png"))
    returned = read_rgb(screens / (NAMES[1] + ".png"))
    panel_region = (*screen_point(680, 602), *screen_point(1250, 712))
    checks = {
        "two_generation_fixture_verified_before_fault":
            a["generation"] == 1 and a["retreats"] == 1
            and b["generation"] == 2 and b["retreats"] == 2,
        "newest_B_corrupted_without_touching_previous_A":
            valid_a == after_a and damaged != valid_b,
        "eleventh_guest_restores_older_retreat_count_into_ZL":
            native_pixel(reloaded, 690, 612) == GOLD
            and native_pixel(reloaded, 789, 681) == PANEL
            and native_pixel(reloaded, 793, 681) == WHITE
            and native_pixel(reloaded, 923, 679) == WHITE
            and _same(field, reloaded, (260, 130, 1000, 580)),
        "eleventh_guest_B_exit_preserves_exact_field_pixels":
            native_pixel(returned, 0, 5) == MAP
            and _same(field, returned, GAME_ROI)
            and _same(field, returned, panel_region),
        "repair_committed_B_as_second_generation_not_third":
            recovered_a == a and recovered_b == b
            and recovered_b["generation"] == 2
            and recovered_b["retreats"] == 2
            and recovered_b["outcome"] == 3
            and recovered_b["experience"] == recovered_b["gella"] == 0,
        "exact_A_unchanged_and_B_byte_equivalent_after_repair":
            after_a == valid_a and after_b == valid_b,
    }
    evidence = {
        "kind": "neXium_eleventh_guest_crc_failure_and_repaired_journal",
        "provenance": "actual_new_guest_process_same_SDMC_after_CRC_corruption",
        "all_checks_passed": all(checks.values()),
        "checks": checks,
        "journal_metadata": {
            "baseline_a": a, "baseline_b": b,
            "repaired_a": recovered_a, "repaired_b": recovered_b,
        },
        "sha256": {
            "corrupted_b": hashlib.sha256(damaged).hexdigest(),
            "repaired_a": hashlib.sha256(after_a).hexdigest(),
            "repaired_b": hashlib.sha256(after_b).hexdigest(),
            **{
                n: hashlib.sha256((screens / (n + ".png")).read_bytes()).hexdigest()
                for n in NAMES
            },
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return evidence


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--screenshots", type=Path, required=True)
    p.add_argument("--original-field", type=Path, required=True)
    p.add_argument("--original-a", type=Path, required=True)
    p.add_argument("--original-b", type=Path, required=True)
    p.add_argument("--corrupted-b", type=Path, required=True)
    p.add_argument("--repaired-a", type=Path, required=True)
    p.add_argument("--repaired-b", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    try:
        report = audit_recovery(
            args.screenshots, args.original_field, args.original_a,
            args.original_b, args.corrupted_b, args.repaired_a,
            args.repaired_b, args.report,
        )
    except (OSError, ValueError, TypeError) as exc:
        p.exit(2, f"11th NeXium battle corruption-recovery audit rejected: {exc}\n")
    print(json.dumps(report["checks"], sort_keys=True))
    if not report["all_checks_passed"]:
        p.exit(1, "11th guest did not recover damaged journal correctly\n")
