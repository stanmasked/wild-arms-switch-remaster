#!/usr/bin/env python3
"""Independent real-NeXium two-area completion screenshot oracle."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops
from audit_nexium_checkpoints import VIEW_X, VIEW_W, VIEW_H
from audit_nexium_field_journal import (
    read_rgb, native_pixel, panel_valid, BLUE, WHITE, SPRITE_RED, EVENT_GOLD
)

NAMES = (
    "00_area0_exit", "01_area1_adjacent", "02_one_clue_open",
    "03_completed_open", "04_completed_closed",
)


def second_area_badge_valid(image):
    # Exact original 18x18 pixels of the blue/white mark, shifted to y=353.
    native = Image.new("RGB", (1280, 720), (17, 26, 40))
    draw = ImageDraw.Draw(native)
    draw.rectangle((569, 353, 586, 370), fill=BLUE)
    for box in ((573, 361, 576, 364), (577, 365, 580, 368),
                (581, 359, 584, 362), (585, 355, 586, 358)):
        draw.rectangle(box, fill=WHITE)
    projected = native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    observed = image.crop((VIEW_X, 0, VIEW_X + VIEW_W, VIEW_H))
    mask_native = Image.new("L", (1280, 720))
    ImageDraw.Draw(mask_native).rectangle((569, 353, 586, 370), fill=255)
    mask = mask_native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    difference = ImageChops.difference(projected, observed)
    return ImageChops.multiply(
        difference, Image.merge("RGB", (mask, mask, mask))).getbbox() is None


def audit_completion(folder, report_path):
    folder = Path(folder)
    if {p.name for p in folder.glob("*.png")} != {n + ".png" for n in NAMES}:
        raise ValueError("incorrect actual guest 2/2 screenshot set")
    images = {n: read_rgb(folder / (n + ".png")) for n in NAMES}
    checks = {
        "area1_reached_by_controller":
            native_pixel(images["01_area1_adjacent"], 564, 284) == SPRITE_RED,
        "second_event_uncollected_before_B":
            native_pixel(images["01_area1_adjacent"], 569, 353) == EVENT_GOLD,
        "first_clue_only_before_second_recording":
            panel_valid(images["02_one_clue_open"], 1),
        "full_panel_and_completion_caption_exact_two_of_two":
            panel_valid(images["03_completed_open"], 2),
        "second_event_full_blue_white_badge":
            second_area_badge_valid(images["04_completed_closed"]),
        "player_unchanged_by_recording_and_journal":
            native_pixel(images["04_completed_closed"], 564, 284) == SPRITE_RED,
    }
    result = {
        "kind": "real_nexium_xvfb_two_area_completion",
        "provenance": "emulator_desktop_screenshot_not_native_framebuffer_or_hardware",
        "all_checks_passed": all(checks.values()),
        "checks": checks,
        "sha256": {
            n: hashlib.sha256((folder / (n + ".png")).read_bytes()).hexdigest()
            for n in NAMES
        },
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_completion(args.screenshots, args.report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Guest completion audit rejected: {exc}\n")
    print(json.dumps(report["checks"], sort_keys=True))
    if not report["all_checks_passed"]:
        parser.exit(1, "Real guest 2/2 screenshot mismatch\n")
