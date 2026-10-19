#!/usr/bin/env python3
"""Stage 309: independent, strict observed-Xvfb audit of the L-held clue ledger.

This checks actual NeXium desktop pixels, not a host-generated screenshot.
The font/sample oracle is deliberately independent of the C++ UI renderer.
Do not mistake desktop RGB evidence for native framebuffer or hardware proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from audit_nexium_checkpoints import SCREEN_SIZE, screen_point

# Source glyph rasters are asserted using an independently authored pixel
# oracle. Samples use the CENTER of each 2x2 native glyph pixel.
GLYPHS = {
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
}
DARK = (17, 26, 40)
WHITE = (246, 247, 252)
BLUE = (105, 160, 230)
EVENT_YELLOW = (255, 247, 172)
SPRITE_RED = (201, 67, 76)
NO_PANEL = (14, 20, 34)
# Bound inputs: no oversized or unbounded directory scanning.
MAX_IMAGE_BYTES = 32 * 1024 * 1024
SCREENSHOTS = (
    "00_empty_open", "01_empty_closed", "02_at_marker",
    "03_inspected", "04_one_open", "05_one_open_right_held",
    "06_one_closed",
)


def read_rgb(path):
    path = Path(path)
    if not path.is_file() or not 32 <= path.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError(f"missing, tiny or oversized screenshot: {path}")
    with Image.open(path) as image:
        image.load()
        if image.size != SCREEN_SIZE:
            raise ValueError(f"unexpected screenshot dimensions: {path}")
        return image.convert("RGB")


def native_pixel(image, x, y):
    return image.getpixel(screen_point(x, y))


def glyph_matches(image, symbol, x, y):
    rows = GLYPHS[symbol]
    for row, pixels in enumerate(rows):
        for col in range(5):
            on = (pixels >> (4 - col)) & 1
            expected = WHITE if on else DARK
            if native_pixel(image, x + 2 * col + 1, y + 2 * row + 1) != expected:
                return False
    return True


def panel_valid(image, clue_count):
    if native_pixel(image, 305, 81) != BLUE:
        return False
    if native_pixel(image, 309, 85) != DARK:
        return False
    if not glyph_matches(image, str(clue_count), 340 + 6 * 14, 116):
        return False
    if not glyph_matches(image, "2", 340 + 8 * 14, 116):
        return False
    if clue_count == 0:
        # Empty journal must leave the entire first-entry glyph area blank.
        for y in range(168, 182):
            for x in range(340, 458):
                if native_pixel(image, x, y) != DARK:
                    return False
    else:
        for symbol, position in (("A", 0), ("0", 1),
                                 ("X", 3), ("Y", 6), ("1", 7)):
            if not glyph_matches(image, symbol, 340 + position * 14, 168):
                return False
        # Two events exist in the intentionally synthetic demo world;
        # discovering one means no second-entry line is displayed.
        for y in range(195, 209):
            for x in range(340, 458):
                if native_pixel(image, x, y) != DARK:
                    return False
    return True


def audit_journal(screenshot_dir, report_file):
    screenshot_dir = Path(screenshot_dir)
    found = {p.name for p in screenshot_dir.glob("*.png")}
    expected = {n + ".png" for n in SCREENSHOTS}
    if found != expected:
        raise ValueError(f"wrong guest journal screenshot set: {sorted(found)}")
    images = {n: read_rgb(screenshot_dir / (n + ".png"))
              for n in SCREENSHOTS}
    checks = {
        "empty_panel_exact_0_of_2": panel_valid(images["00_empty_open"], 0),
        "initial_view_released": native_pixel(images["01_empty_closed"],
                                              305, 81) == NO_PANEL,
        "two_moves_to_adjacent_tile":
            native_pixel(images["02_at_marker"], 500, 220) == SPRITE_RED,
        "inspected_event_outline":
            native_pixel(images["03_inspected"], 552, 208) == EVENT_YELLOW,
        "recorded_panel_exact_1_of_2": panel_valid(images["04_one_open"], 1),
        "held_L_plus_right_still_same_panel":
            panel_valid(images["05_one_open_right_held"], 1),
        "journal_released_and_player_did_not_move":
            native_pixel(images["06_one_closed"], 305, 81) == NO_PANEL
            and native_pixel(images["06_one_closed"], 500, 220) == SPRITE_RED,
    }
    success = all(checks.values())
    report = {
        "kind": "nexium_real_xvfb_manual_clue_journal",
        "provenance": "emulator_desktop_observation_not_hardware_or_native_buffer",
        "switch_inputs": ["L", "DRight", "A", "B"],
        "open_release_collect_reopen_confirmed": success,
        "checks": checks,
        "observed_png_sha256": {
            name: hashlib.sha256((screenshot_dir / (name + ".png")).read_bytes()).hexdigest()
            for name in SCREENSHOTS
        },
    }
    report_file = Path(report_file)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_journal(args.screenshots, args.report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"NeXium journal audit rejected: {exc}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["open_release_collect_reopen_confirmed"]:
        parser.exit(1, "Real NeXium journal evidence failed strict validation\n")


if __name__ == "__main__":
    main()
