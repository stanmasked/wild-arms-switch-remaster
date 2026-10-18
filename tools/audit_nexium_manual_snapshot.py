#!/usr/bin/env python3
"""Audit actual NeXium manual Y/Minus quicksave screenshots.

Proves two visible state restoration sequences from the running guest.
Uses exact projected RGB references at known phases, not the native GPU
framebuffer, and excludes only the already documented host FPS HUD.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

from audit_field_capture import NAMES
from audit_nexium_checkpoints import (
    GAME_ROI, SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, load_references,
    screen_point,
)
from audit_nexium_pixel_parity import compare_scene

# Sequence must be captured after physical X (Switch B) leaves autoplay.
# Keyboard mapping from NeXium controller_config.rs:
# Switch B=X, Y=Z, Minus=N, A=C, DRight=ArrowRight.
PHASES = (
    ("00_manual_start", 0),
    ("01_start_saved", 0),
    ("02_event_after_walk", 1),
    ("03_start_restored", 0),
    ("04_event_again", 1),
    ("05_event_saved", 1),
    ("06_event_acknowledged", None),
    ("07_event_restored", 1),
)
ACK_BAR = (63, 191, 138)
ACK_SPRITE = (201, 67, 76)


def audit_manual_snapshot(reference_dir, screenshot_dir, report_file):
    reference_dir = Path(reference_dir)
    screenshot_dir = Path(screenshot_dir)
    report_file = Path(report_file)
    if reference_dir.resolve() == screenshot_dir.resolve():
        raise ValueError("manual guest screenshots must not alias host references")
    load_references(reference_dir)  # Verify five source PNG/RGB digests first.
    required = {name + ".png" for name, _ in PHASES}
    present = {p.name for p in screenshot_dir.glob("*.png")}
    if present != required:
        raise ValueError(f"wrong manual guest screenshot set: {sorted(present)}")

    records = []
    for phase, ref_index in PHASES:
        observed_path = screenshot_dir / (phase + ".png")
        observed_sha = hashlib.sha256(observed_path.read_bytes()).hexdigest()
        if ref_index is not None:
            reference_path = reference_dir / (NAMES[ref_index] + ".png")
            parity = compare_scene(reference_path, observed_path)
            matched = parity["exact_visible_rgb_match"]
            records.append({
                "phase": phase,
                "reference": NAMES[ref_index],
                "observed_sha256": observed_sha,
                "visible_pixels_compared": parity["visible_pixels_compared"],
                "mismatched_visible_pixels": parity["mismatched_visible_pixels"],
                "matched": matched,
            })
        else:
            with Image.open(observed_path) as png:
                png.load()
                if png.size != SCREEN_SIZE:
                    raise ValueError("acknowledgement screenshot dimensions invalid")
                rgb = png.convert("RGB")
                bar_locations = ((700, 5), (950, 5), (1100, 5))
                bar_ok = all(rgb.getpixel(pos) == ACK_BAR for pos in bar_locations)
                # Foreground sample is intentionally outside the dark facing
                # marker. Position is the area-0 event tile (x4,y1).
                sample_x, sample_y = screen_point(576 - 12, 232 - 12)
                sprite_ok = rgb.getpixel((sample_x, sample_y)) == ACK_SPRITE
                with Image.open(screenshot_dir / "05_event_saved.png") as saved:
                    saved.load()
                    changed = ImageChops.difference(
                        saved.convert("RGB").crop(GAME_ROI),
                        rgb.crop(GAME_ROI),
                    ).getbbox() is not None
            records.append({
                "phase": phase,
                "reference": "acknowledged_area0_event_visual_contract",
                "observed_sha256": observed_sha,
                "green_unpaused_bar": bar_ok,
                "red_player_at_event": sprite_ok,
                "visible_game_roi_changed_from_paused_event": changed,
                "matched": bar_ok and sprite_ok and changed,
            })

    success = all(entry["matched"] for entry in records)
    report = {
        "kind": "nexium_manual_quicksave_real_xvfb_screenshots",
        "provenance": "emulator_desktop_rgb_not_native_gpu_buffer",
        "source_reference": "same_commit_synthetic_host_frames",
        "guest_viewport": [VIEW_X, 0, VIEW_W, VIEW_H],
        "tested_switch_inputs": ["B", "Y", "DRight", "Minus", "A"],
        "manual_quicksave_and_event_restore_confirmed": success,
        "phases": records,
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_manual_snapshot(args.reference, args.screenshots,
                                       args.report)
    except (OSError, ValueError, KeyError, TypeError) as err:
        parser.exit(2, f"Manual NeXium snapshot audit rejected: {err}\n")
    print(json.dumps({
        "manual_quicksave_and_event_restore_confirmed":
            result["manual_quicksave_and_event_restore_confirmed"],
        "phases": len(result["phases"]),
    }, sort_keys=True))
    if not result["manual_quicksave_and_event_restore_confirmed"]:
        parser.exit(1, "Manual quicksave guest visual proof FAILED\n")


if __name__ == "__main__":
    main()
