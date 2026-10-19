#!/usr/bin/env python3
"""Stages 309/323: strict observed-Xvfb audit of the L journal and revisited clue caption.

This checks actual NeXium desktop pixels, not a host-generated screenshot.
The font/sample oracle is deliberately independent of the C++ UI renderer.
Do not mistake desktop RGB evidence for native framebuffer or hardware proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageChops

from audit_nexium_checkpoints import SCREEN_SIZE, screen_point, VIEW_X, VIEW_W, VIEW_H

# Original bitmap glyph contract, reproduced independently in Python.
# Full projected panel is compared pixel-by-pixel; no glyph samples are masked.
GLYPHS = {
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "/": (1, 1, 2, 4, 8, 16, 16),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
}
DARK = (17, 26, 40)
WHITE = (246, 247, 252)
BLUE = (105, 160, 230)
EVENT_YELLOW = (255, 247, 172)
EVENT_GOLD = (245, 183, 66)
SPRITE_RED = (201, 67, 76)
NO_PANEL = (14, 20, 34)
# Bound inputs: no oversized or unbounded directory scanning.
MAX_IMAGE_BYTES = 32 * 1024 * 1024
SCREENSHOTS = (
    "00_empty_open", "01_empty_closed", "02_at_marker",
    "03_inspected", "04_one_open", "05_one_open_right_held",
    "06_one_closed", "07_previous_caption_expired",
    "08_revisited_noted", "09_revisit_journal",
    "10_revisit_expired",
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


def _paint_text(draw, text, x, y):
    for index, symbol in enumerate(text):
        if symbol == " ":
            continue
        for row, pixels in enumerate(GLYPHS[symbol]):
            for col in range(5):
                if (pixels >> (4 - col)) & 1:
                    left = x + index * 14 + col * 2
                    top = y + row * 2
                    draw.rectangle((left, top, left + 1, top + 1), fill=WHITE)


def _expected_panel(clue_count):
    # Independent raster oracle: the full panel, count, and all glyphs
    # must match, not just a handful of positive sample points.
    native = Image.new("RGB", (1280, 720), DARK)
    draw = ImageDraw.Draw(native)
    draw.rectangle((304, 80, 975, 639), fill=BLUE)
    draw.rectangle((308, 84, 971, 635), fill=DARK)
    _paint_text(draw, f"CLUES {clue_count}/2", 340, 116)
    if clue_count:
        _paint_text(draw, "A0 X4 Y1", 340, 168)
    return native


def panel_valid(image, clue_count):
    expected = _expected_panel(clue_count).resize(
        (VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    observed = image.crop((VIEW_X, 0, VIEW_X + VIEW_W, VIEW_H))
    # Compare exactly the projected native UI rectangle; the original
    # game underneath the panel and the emulator HUD are not part of it.
    native_mask = Image.new("L", (1280, 720))
    ImageDraw.Draw(native_mask).rectangle((304, 80, 975, 639), fill=255)
    mask = native_mask.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    delta = ImageChops.difference(expected, observed)
    mask_rgb = Image.merge("RGB", (mask, mask, mask))
    return ImageChops.multiply(delta, mask_rgb).getbbox() is None


def revisited_caption_valid(image):
    # Independent full-panel pixel oracle for the blue CLUE NOTED caption.
    # A border-only test would accept missing/incorrect glyphs.
    # This panel is deliberately right-aligned away from NeXium's HUD.
    native = Image.new("RGB", (1280, 720), NO_PANEL)
    draw = ImageDraw.Draw(native)
    draw.rectangle((1000, 34, 1237, 88), fill=BLUE)
    draw.rectangle((1003, 37, 1234, 85), fill=DARK)
    for index, symbol in enumerate("CLUE NOTED"):
        if symbol == " ":
            continue
        for row, pattern in enumerate(GLYPHS[symbol]):
            for col in range(5):
                if (pattern >> (4 - col)) & 1:
                    x = 1020 + index * 15 + col * 2
                    y = 54 + row * 2
                    draw.rectangle((x, y, x + 1, y + 1), fill=WHITE)

    projected = native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    observed = image.crop((VIEW_X, 0, VIEW_X + VIEW_W, VIEW_H))
    mask_native = Image.new("L", (1280, 720))
    ImageDraw.Draw(mask_native).rectangle((1000, 34, 1237, 88), fill=255)
    mask = mask_native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    delta = ImageChops.difference(projected, observed)
    return ImageChops.multiply(
        delta, Image.merge("RGB", (mask, mask, mask))).getbbox() is None


def discovered_badge_valid(image):
    """Full 18x18 native badge, projected to actual guest desktop pixels.

    This oracle is independent of the C++ raster helper and compares all
    checkmark/border pixels without ignoring unexpected colors.
    """
    native = Image.new("RGB", (1280, 720), DARK)
    brush = ImageDraw.Draw(native)
    brush.rectangle((569, 225, 586, 242), fill=BLUE)
    for x0, y0, x1, y1 in (
        (573, 233, 576, 236),
        (577, 237, 580, 240),
        (581, 231, 584, 234),
        (585, 227, 586, 230),
    ):
        brush.rectangle((x0, y0, x1, y1), fill=WHITE)

    expected = native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    observed = image.crop((VIEW_X, 0, VIEW_X + VIEW_W, VIEW_H))
    native_mask = Image.new("L", (1280, 720))
    ImageDraw.Draw(native_mask).rectangle((569, 225, 586, 242), fill=255)
    mask = native_mask.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    delta = ImageChops.difference(expected, observed)
    return ImageChops.multiply(
        delta, Image.merge("RGB", (mask, mask, mask))).getbbox() is None


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
        "uncollected_marker_has_no_blue_badge":
            native_pixel(images["02_at_marker"], 569, 225) == EVENT_GOLD,
        "collected_clue_renders_complete_in_world_badge":
            discovered_badge_valid(images["06_one_closed"]) and
            discovered_badge_valid(images["08_revisited_noted"]) and
            discovered_badge_valid(images["10_revisit_expired"]),
        "held_L_plus_right_still_same_panel":
            panel_valid(images["05_one_open_right_held"], 1),
        "journal_released_and_player_did_not_move":
            native_pixel(images["06_one_closed"], 305, 81) == NO_PANEL
            and native_pixel(images["06_one_closed"], 500, 220) == SPRITE_RED,
        "old_caption_expired_before_reinspection":
            native_pixel(images["07_previous_caption_expired"], 1000, 34) ==
            NO_PANEL and
            native_pixel(images["07_previous_caption_expired"], 500, 220) ==
            SPRITE_RED,
        "revisited_clue_noted_entire_caption_rgb":
            revisited_caption_valid(images["08_revisited_noted"]),
        "revisited_still_outlines_authored_event":
            native_pixel(images["08_revisited_noted"], 552, 208) ==
            EVENT_YELLOW,
        "revisited_journal_remains_one_of_two":
            panel_valid(images["09_revisit_journal"], 1),
        "revisited_caption_expires_without_player_movement":
            native_pixel(images["10_revisit_expired"], 1000, 34) == NO_PANEL
            and native_pixel(images["10_revisit_expired"], 500, 220) ==
            SPRITE_RED,
    }
    success = all(checks.values())
    report = {
        "kind": "nexium_real_xvfb_manual_clue_journal",
        "provenance": "emulator_desktop_observation_not_hardware_or_native_buffer",
        "switch_inputs": ["L", "DRight", "A", "B", "A_reinspect", "L_reopen"],
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
