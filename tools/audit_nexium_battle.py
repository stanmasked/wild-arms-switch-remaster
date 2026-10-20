#!/usr/bin/env python3
"""Strict real-NeXium R/A/B battle route screenshot oracle.

Compare guest desktop frames to same-commit, independently rendered
host battle frames; then require the field to be restored on closing B.
This verifies *experimental emulator* pixels, not a native GPU capture
or physical Switch console.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H
from audit_nexium_pixel_parity import HUD_MASK, compare_scene

SHOTS = (
    "00_field_before", "01_battle_open", "02_battle_strike",
    "03_field_return", "04_battle_reopen",
)
REFERENCES = (
    "battle-preview-initial.png", "battle-preview-strike.png",
)
MAX_BYTES = 32 * 1024 * 1024


def _desktop(path):
    path = Path(path)
    if not path.is_file() or not 32 <= path.stat().st_size <= MAX_BYTES:
        raise ValueError(f"invalid or missing guest screenshot: {path}")
    with Image.open(path) as img:
        img.load()
        if img.size != SCREEN_SIZE:
            raise ValueError(f"incorrect Xvfb desktop dimensions: {path}")
        return img.convert("RGB")


def masked_game(screen):
    observed = screen.crop((VIEW_X, 0, VIEW_X + VIEW_W, VIEW_H))
    x, y, w, h = HUD_MASK
    ImageDraw.Draw(observed).rectangle(
        (x, y, x + w - 1, y + h - 1), fill=(0, 0, 0))
    return observed


def audit_battle(reference_dir, screenshots_dir, report_path):
    reference_dir = Path(reference_dir)
    screenshots_dir = Path(screenshots_dir)
    if reference_dir.resolve() == screenshots_dir.resolve():
        raise ValueError("host references must not alias guest screenshots")
    if {p.name for p in screenshots_dir.glob("*.png")} != {
            x + ".png" for x in SHOTS}:
        raise ValueError("expected exactly five named guest screenshots")
    for name in REFERENCES:
        p = reference_dir / name
        if not p.is_file() or not 32 <= p.stat().st_size <= MAX_BYTES:
            raise ValueError(f"missing or invalid host reference: {p}")
        with Image.open(p) as im:
            if im.size != (1280, 720):
                raise ValueError("expected native 1280x720 host reference")

    images = {s: _desktop(screenshots_dir / (s + ".png")) for s in SHOTS}
    initial = compare_scene(
        reference_dir / REFERENCES[0],
        screenshots_dir / "01_battle_open.png")
    strike = compare_scene(
        reference_dir / REFERENCES[1],
        screenshots_dir / "02_battle_strike.png")
    reopened = compare_scene(
        reference_dir / REFERENCES[0],
        screenshots_dir / "04_battle_reopen.png")

    field_before = masked_game(images["00_field_before"])
    field_after = masked_game(images["03_field_return"])
    field_mismatch = ImageChops.difference(
        field_before, field_after).getbbox() is not None
    # The initial field must actually be visually unlike the battle:
    # otherwise an unresponsive guest could falsely pass a roundtrip.
    battle_distinct = ImageChops.difference(
        field_before, masked_game(images["01_battle_open"])).getbbox() is not None
    transition_distinct = ImageChops.difference(
        masked_game(images["01_battle_open"]),
        masked_game(images["02_battle_strike"])).getbbox() is not None
    checks = {
        "battle_entered_after_R_exact_host_RGB":
            initial["exact_visible_rgb_match"],
        "strike_after_A_exact_host_RGB":
            strike["exact_visible_rgb_match"],
        "field_restored_after_B_exact_RGB":
            not field_mismatch,
        "battle_reopened_after_R_exact_initial_RGB":
            reopened["exact_visible_rgb_match"],
        "original_field_distinct_from_battle":
            battle_distinct,
        "strike_visibly_changed_battle":
            transition_distinct,
    }
    result = {
        "kind": "nexium_real_guest_battle_R_A_B_R_roundtrip",
        "provenance": "xvfb_guest_desktop_not_native_gpu_or_physical_switch",
        "exact_reference_commit": "same_workflow_checkout",
        "excluded_performance_overlay_relative": list(HUD_MASK),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "battle_open": initial,
        "battle_strike": strike,
        "battle_reopen": reopened,
        "sha256": {s: hashlib.sha256(
            (screenshots_dir / (s + ".png")).read_bytes()).hexdigest()
                   for s in SHOTS},
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", required=True, type=Path)
    p.add_argument("--screenshots", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    a = p.parse_args()
    try:
        report = audit_battle(a.reference, a.screenshots, a.report)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        p.exit(2, f"NeXium battle evidence rejected: {exc}\n")
    print(json.dumps(report["checks"], sort_keys=True))
    if not report["all_checks_passed"]:
        p.exit(1, "NeXium guest battle route failed exact RGB evidence\n")
