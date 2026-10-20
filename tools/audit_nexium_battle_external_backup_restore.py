#!/usr/bin/env python3
"""Stage371: verify real isolated NeXium boots from a SHA-pinned offline WABJ.

Not an SDMC recovery button: the CI harness copies the explicitly staged
single valid backup into a NEW root; the two corrupt live slots are untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import ImageChops
from audit_nexium_checkpoints import GAME_ROI, screen_point
from audit_nexium_field_journal import read_rgb, native_pixel
from audit_nexium_battle_persistence import read_journal
from audit_nexium_battle_alternating_faults import four_rewards, GREEN, GOLD
from audit_nexium_battle_double_corruption import digit
from audit_nexium_battle_corruption_warning import WHITE, banner

FRAMES = (
    "00_twentyfifth_restore_four_wins",
    "01_twentyfifth_after_retreat",
    "02_twentyfifth_saved_after_retreat",
    "03_twentysixth_reload_saved_four_wins",
)
PANEL_RECT = (*screen_point(680, 602), *screen_point(1250, 712))


def same(a, b, rect):
    return ImageChops.difference(a.crop(rect), b.crop(rect)).getbbox() is None


def guest_pids(prior, new):
    all_rows = Path(prior).read_text(encoding="ascii").splitlines()
    all_rows += Path(new).read_text(encoding="ascii").splitlines()
    expected = ("twentythird", "twentyfourth", "twentyfifth", "twentysixth")
    if len(all_rows) != 4:
        raise ValueError("expected four genuine labelled NeXium process PIDs")
    ids = []
    for name, row in zip(expected, all_rows):
        parts = row.split()
        if len(parts) != 2 or parts[0] != name or not parts[1].isdigit():
            raise ValueError("wrong guest PID provenance")
        ids.append(int(parts[1]))
    if len(set(ids)) != 4 or min(ids) <= 0:
        raise ValueError("NeXium guest process IDs not independent")
    return ids


def guest_keys(path):
    events = Path(path).read_text(encoding="ascii").splitlines()
    expected = (("twentyfifth", "x"), ("twentyfifth", "e"),
                ("twentyfifth", "x"), ("twentysixth", "x"))
    if len(events) != len(expected):
        raise ValueError("expected four distinct, no-A key edges")
    for row, (label, key) in zip(events, expected):
        fields = row.split()
        if (len(fields) != 3 or fields[0] != label or
                fields[2] != key or not fields[1].endswith("Z")):
            raise ValueError("wrong controller key event provenance")
    return True


def audit_external_recovery(screens, prior_field, staged_a,
                            original_corrupt_a, original_corrupt_b,
                            live_corrupt_a, live_corrupt_b,
                            after25_a, after25_b, after26_a, after26_b,
                            manifest, prior_pids, new_pids, keys, report):
    root = Path(screens)
    want = {name + ".png" for name in FRAMES}
    found = {p.name for p in root.glob("*.png")}
    if found != want:
        raise ValueError(f"missing/extra actual guest screenshots: {sorted(want ^ found)}")
    images = [read_rgb(root / (name + ".png")) for name in FRAMES]
    initial, field25, after25, reload26 = images
    field = read_rgb(prior_field)
    # Original damaged evidence and the live-source snapshots MUST be four
    # distinct physical files. Aliasing them makes "unchanged" vacuous.
    source_paths = [Path(p) for p in (
        original_corrupt_a, original_corrupt_b, live_corrupt_a, live_corrupt_b)]
    inode_ids = [(p.stat().st_dev, p.stat().st_ino) for p in source_paths]
    if len(set(inode_ids)) != len(inode_ids):
        raise ValueError("original and live corrupt evidence must be independent files")
    original = [Path(path).read_bytes() for path in
                (original_corrupt_a, original_corrupt_b)]
    live = [Path(path).read_bytes() for path in
            (live_corrupt_a, live_corrupt_b)]
    if not all(len(blob) == 52 and blob[:4] == b"WABJ" for blob in original):
        raise ValueError("missing Stage369 damaged slot evidence")
    for path in (original_corrupt_a, original_corrupt_b, live_corrupt_a, live_corrupt_b):
        try:
            read_journal(path)
        except ValueError:
            pass
        else:
            raise ValueError("supposed damaged source file is valid")
    staged = read_journal(staged_a)
    p25_a = read_journal(after25_a)
    p25_b = read_journal(after25_b)
    p26_a = read_journal(after26_a)
    p26_b = read_journal(after26_b)
    raw25_a = Path(after25_a).read_bytes()
    raw25_b = Path(after25_b).read_bytes()
    raw26_a = Path(after26_a).read_bytes()
    raw26_b = Path(after26_b).read_bytes()
    raw_staged = Path(staged_a).read_bytes()
    file_manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
    ids = guest_pids(prior_pids, new_pids)
    guest_keys(keys)
    checks = {
        "two_corrupt_originals_preserved_without_mutation":
            original == live,
        "trusted_gen6_backup_restored_only_into_separate_new_root":
            staged["generation"] == 6 and staged["wins"] == 4
            and staged["retreats"] == 2
            and staged["experience"] == 32 and staged["gella"] == 48
            and file_manifest["installed_to_live_sdmc"] is False
            and file_manifest["recovered"] == staged
            and file_manifest["verified_backup_sha256"] == staged["sha256"],
        "twentyfifth_fresh_boot_reads_four_wins_32EXP_48Gella":
            four_rewards(initial)
            and digit(initial, 789, 677, 2, WHITE, sample_y=0)
            and not banner(initial),
        "twentyfifth_retreat_returns_unmodified_original_field":
            native_pixel(field25, 0, 5) == GREEN
            and same(field, field25, GAME_ROI)
            and same(field, field25, PANEL_RECT),
        "twentyfifth_retreat_renders_four_wins_three_exits_no_payout":
            four_rewards(after25)
            and digit(after25, 789, 677, 3, WHITE, sample_y=0)
            and not banner(after25),
        "independent_twentyfifth_save_writes_generation_seven_B":
            p25_b["generation"] == 7 and p25_b["outcome"] == 3
            and p25_b["wins"] == 4 and p25_b["retreats"] == 3
            and p25_b["experience"] == 32 and p25_b["gella"] == 48,
        "isolated_new_SDMC_keeps_staged_gen6_A_unmodified":
            raw25_a == raw_staged == raw26_a and p25_a == staged == p26_a,
        "twentysixth_fresh_boot_exactly_restores_retreat_and_rewards":
            four_rewards(reload26)
            and digit(reload26, 789, 677, 3, WHITE, sample_y=0)
            and same(after25, reload26, GAME_ROI)
            and same(after25, reload26, PANEL_RECT)
            and not banner(reload26),
        "twentysixth_read_only_reboot_never_rewrites_new_B":
            raw25_b == raw26_b and p25_b == p26_b,
        "offline_staging_never_imports_or_double_awards":
            all(item["wins"] == 4 and item["experience"] == 32
                and item["gella"] == 48 for item in (staged,p25_a,p25_b,p26_a,p26_b)),
        "four_guest_PIDs_distinct_and_no_attack_edges":
            len(set(ids)) == 4,
    }
    result = {
        "kind": "stage371_real_guest_isolated_explicit_external_backup_restoration",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "sha256": {
            **{name: hashlib.sha256((root/(name+".png")).read_bytes()).hexdigest()
               for name in FRAMES},
            "isolated_staged_gen6_a": staged["sha256"],
            "after25_gen7_b": p25_b["sha256"],
            "original_corrupt_a": hashlib.sha256(original[0]).hexdigest(),
            "original_corrupt_b": hashlib.sha256(original[1]).hexdigest(),
        },
        "journals": {"staged_gen6":staged,"after25_gen6_a":p25_a,
                     "after25_gen7_b":p25_b,"after26_gen6_a":p26_a,
                     "after26_gen7_b":p26_b},
    }
    dest = Path(report)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return result


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    names=("screens prior-field staged-a original-corrupt-a original-corrupt-b "
           "live-corrupt-a live-corrupt-b after25-a after25-b after26-a after26-b "
           "manifest prior-pids new-pids keys report").split()
    for name in names:
        p.add_argument("--"+name, required=True)
    a=p.parse_args()
    try:
        result=audit_external_recovery(*(getattr(a,x.replace("-","_")) for x in names))
    except (ValueError, OSError, TypeError) as e:
        p.exit(2,f"Stage371 isolated recovered guest audit rejected: {e}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        p.exit(1,"Stage371 NeXium recovered-save evidence is invalid\n")
