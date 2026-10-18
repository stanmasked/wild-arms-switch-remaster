#!/usr/bin/env python3
"""Compare GUI screenshots with/without an NRO; does not prove guest execution."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


def signature(path):
    path = Path(path)
    with Image.open(path) as img:
        img.load()
        if not (640 <= img.width <= 4096 and 480 <= img.height <= 4096):
            raise ValueError("unexpected desktop capture size")
        rgb = img.convert("RGB")
        histogram = rgb.histogram()
        channel_total = sum(histogram)
        # Saturated Xvfb splash border and near-black background.
        dark_channels = sum(histogram[i] for i in range(0, 40))
        return {
            "name": path.name,
            "size": [rgb.width, rgb.height],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "dark_channel_fraction": round(dark_channels / channel_total, 6),
        }


def compare_screen(guest_file, control_file):
    a_path = Path(guest_file)
    b_path = Path(control_file)
    with Image.open(a_path) as a, Image.open(b_path) as b:
        a.load()
        b.load()
        if a.size != b.size:
            raise ValueError("guest and control desktop images have different sizes")
        if not (640 <= a.width <= 4096 and 480 <= a.height <= 4096):
            raise ValueError("unexpected desktop capture size")
        delta = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
        # Fraction of image colour channels within 16/255. "Similar"
        # describes the desktop images, NOT emulated game correctness.
        hist = delta.histogram()
        close_channels = sum(hist[i] for base in (0, 256, 512)
                             for i in range(base, base + 17))
        fraction = close_channels / (a.width * a.height * 3)
    return round(fraction, 6)


def diagnose(guest_file, control_file, report_file):
    a, b = Path(guest_file), Path(control_file)
    comparison = {
        "kind": "nexium_gui_with_without_nro_screen_comparison",
        "not_emulator_gameplay_verification": True,
        "guest": signature(a),
        "no_nro_control": signature(b),
        "within_16_channel_fraction": compare_screen(a, b),
    }
    comparison["visually_similar_desktop"] = (
        comparison["within_16_channel_fraction"] >= 0.98)
    report_file = Path(report_file)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(comparison, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return comparison


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--guest", type=Path, required=True)
    p.add_argument("--no-nro", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    try:
        value = diagnose(a.guest, a.no_nro, a.report)
    except (OSError, ValueError) as err:
        p.exit(2, f"GUI control comparison invalid: {err}\n")
    print(json.dumps({
        "within_16_channel_fraction": value["within_16_channel_fraction"],
        "visually_similar_desktop": value["visually_similar_desktop"]
    }))


if __name__ == "__main__":
    main()
