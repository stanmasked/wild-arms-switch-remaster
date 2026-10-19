#!/usr/bin/env python3
"""Verify actual NeXium storage plaques against every projected RGB pixel.

Uses the measured 1600x900 Xvfb + 1234x694 guest nearest-neighbour view,
excluding the outermost three desktop pixels of the plaque boundary.
This is guest-desktop evidence, NOT native 1280x720 GPU framebuffer
extraction or proof that writes survive abrupt hardware power loss.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from audit_nexium_checkpoints import (
    SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, screen_point,
)

SAVE_COLORS = {
    (56, 207, 125): "sd_saved",
    (244, 178, 64): "ram_only",
    (231, 77, 91): "sd_error",
}
LOAD_COLORS = {(104, 149, 244): "ram_loaded"}
# This color must NOT be accepted in same-process quicksave tests: fresh
# process SD import is proved only by the dedicated Stage-297 audit.
SD_LOADED_COLOR = (73, 181, 225)
RESTART_COLORS = {SD_LOADED_COLOR: "sd_loaded"}
CAPTURES = (
    ("save-start", SAVE_COLORS),
    ("load-start", LOAD_COLORS),
    ("save-event", SAVE_COLORS),
    ("load-event", LOAD_COLORS),
)
MESSAGES = {
    "sd_saved": "SD SAVED",
    "ram_only": "RAM ONLY",
    "sd_error": "SD ERROR",
    "ram_loaded": "RAM LOADED",
    "sd_loaded": "SD LOADED",
}
# Independent reference to the seven-row glyphs in field_save_feedback.hpp.
GLYPHS = {
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    " ": (0, 0, 0, 0, 0, 0, 0),
}
WHITE = (245, 247, 252)
DARK = (17, 26, 40)
RECT = (982, 29, 270, 51)
MAX_SCREEN_BYTES = 32 * 1024 * 1024
# NeXium scales the game with nearest neighbour. Inspect the whole notice
# except a 3-desktop-pixel boundary to exclude mixing with the scene below.
LEFT, TOP = screen_point(RECT[0], RECT[1])
RIGHT, BOTTOM = screen_point(RECT[0] + RECT[2], RECT[1] + RECT[3])
GAME_ROI = (LEFT + 3, TOP + 3, RIGHT - 3, BOTTOM - 3)


def projected_notice(color, label=None):
    """Pure reference drawing, independent from the game's output buffer."""
    notice = SAVE_COLORS.get(
        color, LOAD_COLORS.get(color, RESTART_COLORS.get(color)))
    if notice is None:
        raise ValueError("unknown status accent")
    wording = MESSAGES[notice] if label is None else label
    native = Image.new("RGB", (1280, 720), (0, 0, 0))
    draw = ImageDraw.Draw(native)
    x, y, w, h = RECT
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=color)
    draw.rectangle((x + 2, y + 2, x + w - 3, y + h - 3), fill=DARK)
    draw.rectangle((x + 14, y + 14, x + 35, y + 36), fill=color)
    for index, c in enumerate(wording[:16]):
        for row, bits in enumerate(GLYPHS[c]):
            for column in range(5):
                if (bits >> (4 - column)) & 1:
                    px = x + 52 + index * 12 + column * 2
                    py = y + 17 + row * 2
                    draw.rectangle((px, py, px + 1, py + 1), fill=WHITE)
    return native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)


def audit_feedback_images(directory, report_path):
    directory, report_path = Path(directory), Path(report_path)
    expected_files = {name + ".png" for name, _ in CAPTURES}
    actual_files = {p.name for p in directory.glob("*.png")}
    if actual_files != expected_files:
        raise ValueError(
            f"expected exactly four feedback screenshots, got {sorted(actual_files)}")
    records = []
    accent_x, accent_y = screen_point(1008, 54)
    target_pixels = (GAME_ROI[2]-GAME_ROI[0]) * (GAME_ROI[3]-GAME_ROI[1])
    for name, palette in CAPTURES:
        path = directory / (name + ".png")
        if not 32 <= path.stat().st_size <= MAX_SCREEN_BYTES:
            raise ValueError("invalid image size: " + name)
        with Image.open(path) as image:
            image.load()
            if image.size != SCREEN_SIZE:
                raise ValueError("unexpected Xvfb image size: " + name)
            observed = image.convert("RGB")
            accent = observed.getpixel((accent_x, accent_y))
            visible = observed.crop(GAME_ROI)
            if accent in palette:
                projected = projected_notice(accent)
                relative_roi = (
                    GAME_ROI[0]-VIEW_X, GAME_ROI[1],
                    GAME_ROI[2]-VIEW_X, GAME_ROI[3],
                )
                expected = projected.crop(relative_roi)
                channel_diff = ImageChops.difference(visible, expected)
                max_channel = channel_diff.split()
                delta = ImageChops.lighter(
                    ImageChops.lighter(max_channel[0],max_channel[1]),
                    max_channel[2])
                mismatch = target_pixels - delta.histogram()[0]
                notice = palette[accent]
            else:
                notice = "unexpected"
                mismatch = target_pixels
        records.append({
            "phase": name,
            "capture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "notice": notice,
            "color_match": accent in palette,
            "compared_projected_plaque_pixels": target_pixels,
            "mismatched_projected_plaque_pixels": mismatch,
            "indicator_valid": accent in palette and mismatch == 0,
        })

    complete = all(rec["indicator_valid"] for rec in records)
    report = {
        "kind": "nexium_real_guest_exact_projected_storage_plaque_rgb",
        "source": "guest_xvfb_screenshot_not_native_gpu_framebuffer",
        "phase_count": len(records),
        "plaque_region_xvfb": list(GAME_ROI),
        "all_four_indicators_valid": complete,
        "total_compared_pixels": target_pixels * len(records),
        "total_mismatched_pixels": sum(rec["mismatched_projected_plaque_pixels"]
                                       for rec in records),
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
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2,f"Storage plaque guest audit rejected: {exc}\n")
    print(json.dumps({
        "all_four_indicators_valid": result["all_four_indicators_valid"],
        "mismatched_pixels": result["total_mismatched_pixels"],
        "pixels_compared": result["total_compared_pixels"],
        "notices": [rec["notice"] for rec in result["records"]],
    },sort_keys=True))
    if not result["all_four_indicators_valid"]:
        parser.exit(1,"Guest storage plaque pixels diverged from exact reference\n")


if __name__ == "__main__":
    main()
