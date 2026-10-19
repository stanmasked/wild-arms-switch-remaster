#!/usr/bin/env python3
"""Audit four actual guest screenshots while the transient save plaque shows.

Only the fixed, measured 1600x900 NeXium Xvfb presentation is supported.
This is NOT direct 1280x720 GPU capture or SD durability verification.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from audit_nexium_checkpoints import SCREEN_SIZE, screen_point

SAVE_COLORS = {
    (56, 207, 125): "sd_saved",
    (244, 178, 64): "ram_only",
    (231, 77, 91): "sd_error",
}
LOAD_COLORS = {(104, 149, 244): "ram_loaded"}
CAPTURES = (
    ("save-start", SAVE_COLORS),
    ("load-start", LOAD_COLORS),
    ("save-event", SAVE_COLORS),
    ("load-event", LOAD_COLORS),
)
WHITE = (245, 247, 252)
MAX_SCREEN_BYTES = 32 * 1024 * 1024


def audit_feedback_images(directory, report_path):
    directory, report_path = Path(directory), Path(report_path)
    expected_files = {name + ".png" for name, _ in CAPTURES}
    actual_files = {p.name for p in directory.glob("*.png")}
    if actual_files != expected_files:
        raise ValueError(f"expected exactly four feedback screenshots, got {sorted(actual_files)}")
    records = []
    accent_x, accent_y = screen_point(1008, 54)
    # 5x7 text raster starts at native x 1034 / y 46, ends below y 60.
    x0,y0 = screen_point(1034, 46)
    x1,y1 = screen_point(1170, 61)
    for name, palette in CAPTURES:
        path = directory / (name + ".png")
        if not 32 <= path.stat().st_size <= MAX_SCREEN_BYTES:
            raise ValueError("invalid image size: " + name)
        with Image.open(path) as image:
            image.load()
            if image.size != SCREEN_SIZE:
                raise ValueError("unexpected Xvfb image size: " + name)
            rgb = image.convert("RGB")
            accent = rgb.getpixel((accent_x, accent_y))
            count = sum(rgb.getpixel((x,y)) == WHITE
                        for y in range(y0, y1) for x in range(x0, x1))
        ok = accent in palette and count >= 18
        records.append({
            "phase": name,
            "capture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "notice": palette.get(accent, "unexpected"),
            "color_match": accent in palette,
            "text_white_pixels": count,
            "indicator_valid": ok,
        })
    complete = all(x["indicator_valid"] for x in records)
    report = {
        "kind": "nexium_real_guest_short_lived_storage_indicators",
        "source": "guest_xvfb_screenshot_not_native_gpu_framebuffer",
        "phase_count": len(records),
        "all_four_indicators_valid": complete,
        "records": records,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n",
                           encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_feedback_images(args.screenshots,args.report)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2,f"Storage feedback guest audit rejected: {exc}\n")
    print(json.dumps({
        "all_four_indicators_valid": result["all_four_indicators_valid"],
        "notices": [r["notice"] for r in result["records"]]
    },sort_keys=True))
    if not result["all_four_indicators_valid"]:
        parser.exit(1,"Guest storage notice evidence missing or incorrect\n")


if __name__ == "__main__":
    main()
