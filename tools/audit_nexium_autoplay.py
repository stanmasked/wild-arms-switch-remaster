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


def status_bar(image, expected):
    return all(image.convert("RGB").getpixel((x, 5)) == expected
               for x in (500, 700, 900))


def audit_frames(initial, intermediate, report_path,
                 require_event_roundtrip=False):
    initial = Path(initial)
    intermediate = [Path(x) for x in intermediate]
    if not intermediate or len({p.resolve() for p in [initial, *intermediate]}) != len(intermediate) + 1:
        raise ValueError("no intermediate screenshots or duplicate paths")
    with Image.open(initial) as base:
        base.load()
        if base.size != EXPECTED_DESKTOP:
            raise ValueError("wrong Xvfb dimensions")
        green_initial = status_bar(base, (63, 191, 138))
        event_seen = False
        last_green = False
        counts = []
        for i, path in enumerate(intermediate):
            with Image.open(path) as frame:
                frame.load()
                if frame.size != base.size:
                    raise ValueError("screenshot dimensions differ")
                counts.append(pixels_changed(base, frame))
                event_seen |= status_bar(frame, (246, 183, 66))
                if i == len(intermediate) - 1:
                    last_green = status_bar(frame, (63, 191, 138))
    changed = any(n >= MIN_CHANGED_PIXELS for n in counts)
    returned = green_initial and last_green and counts[-1] == 0
    strict_ok = changed and event_seen and returned
    report = {
        "kind": "nexium_guest_field_visual_transition",
        "input_key_host": "v",
        "switch_button_intended": "X",
        "game_roi": list(VIEW_CROP),
        "max_changed_pixels": max(counts),
        "changed_by_capture": [
            {"file": path.name, "changed_pixels": number}
            for path, number in zip(intermediate, counts)],
        "visual_transition_confirmed": changed,
        "event_status_bar_detected": event_seen,
        "round_trip_field_identical": returned,
        "event_and_roundtrip_observed": strict_ok,
        "strict_event_roundtrip_required": require_event_roundtrip,
        "controller_event_authenticity_confirmed": False,
        "checkpoint_parity_confirmed": False,
        "status": ("event_and_roundtrip_observed" if strict_ok else
                   "field_pixels_changed" if changed else
                   "no_visible_field_transition"),
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
    p.add_argument("--require-event-roundtrip", action="store_true")
    args = p.parse_args()
    try:
        report = audit_frames(args.initial, args.intermediate, args.report,
                              require_event_roundtrip=args.require_event_roundtrip)
    except (OSError, ValueError) as exc:
        p.exit(2, f"Autoplay visual evidence rejected: {exc}\n")
    print(json.dumps({"status": report["status"],
                      "max_changed_pixels": report["max_changed_pixels"]}))
    if not report["visual_transition_confirmed"] or (
            args.require_event_roundtrip and
            not report["event_and_roundtrip_observed"]):
        p.exit(1, "No visible field movement in expected game region\n")


if __name__ == "__main__":
    main()
