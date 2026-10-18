#!/usr/bin/env python3
"""Verify observable field movement in real NeXium desktop screenshots.

This is a visual transition check on a fixed Xvfb layout, not proof of
authentic controller events or full gameplay parity.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops

MIN_CHANGED_PIXELS = 180
# Map occupies the center of a 1600x900 Xvfb desktop at fixed 1280x720
# guest resolution. Exclude NeXium FPS overlay, status chrome and menus.
VIEW_CROP = (260, 110, 1040, 600)
EXPECTED_DESKTOP = (1600, 900)


def pixels_changed(first, second, crop=VIEW_CROP, threshold=12):
    if first.size != second.size:
        raise ValueError("screenshots have differing sizes")
    x0, y0, x1, y1 = crop
    if x0 < 0 or y0 < 0 or x1 > first.width or y1 > first.height:
        raise ValueError("game crop does not fit screenshots")
    a = first.convert("RGB").crop(crop)
    b = second.convert("RGB").crop(crop)
    delta = ImageChops.difference(a, b).convert("RGB")
    return sum(max(pixel) >= threshold for pixel in delta.getdata())


def audit_frames(initial, intermediate, report_path):
    initial = Path(initial)
    intermediate = [Path(x) for x in intermediate]
    if not intermediate:
        raise ValueError("at least one intermediate capture required")
    frames = [initial, *intermediate]
    if len(set(p.resolve() for p in frames)) != len(frames):
        raise ValueError("duplicate screenshot path")
    with Image.open(initial) as reference:
        reference.load()
        if reference.size != EXPECTED_DESKTOP:
            raise ValueError("unexpected virtual desktop size")
        counts = []
        for shot in intermediate:
            with Image.open(shot) as image:
                image.load()
                if image.size != reference.size:
                    raise ValueError("screenshot dimensions differ")
                counts.append(pixels_changed(reference, image))
    changed = any(value >= MIN_CHANGED_PIXELS for value in counts)
    report = {
        "kind": "nexium_guest_field_visual_transition",
        "input_key_host": "v",
        "switch_button_intended": "X",
        "requires_real_game_field": True,
        "game_roi": list(VIEW_CROP),
        "max_changed_pixels": max(counts),
        "changed_by_capture": [
            {"file": path.name, "changed_pixels": num}
            for path, num in zip(intermediate, counts)
        ],
        "visual_transition_confirmed": changed,
        "controller_event_authenticity_confirmed": False,
        "checkpoint_parity_confirmed": False,
        "status": ("field_pixels_changed" if changed else "no_visible_field_transition"),
    }
    output = Path(report_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--intermediate", nargs="+", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    try:
        report = audit_frames(args.initial, args.intermediate, args.report)
    except (OSError, ValueError) as exc:
        p.exit(2, f"Autoplay visual evidence rejected: {exc}\n")
    print(json.dumps({"status": report["status"],
                      "max_changed_pixels": report["max_changed_pixels"]}))
    if not report["visual_transition_confirmed"]:
        p.exit(1, "No visible field movement in expected game region\n")


if __name__ == "__main__":
    main()
