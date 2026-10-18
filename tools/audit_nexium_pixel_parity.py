#!/usr/bin/env python3
"""Verify exact RGB equality after NeXium's known nearest-neighbour scaling.

The comparison covers the visible 1234x694 guest rectangle except the
NeXium performance overlay. This is NOT direct native 1280x720 GPU capture.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from audit_field_capture import NAMES, WIDTH, HEIGHT
from audit_nexium_checkpoints import (
    SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, load_references,
)

# NeXium's on-screen performance HUD obscures the upper left of the
# otherwise pixel-exact projected framebuffer in the fixed Xvfb layout.
HUD_MASK = (0, 0, 220, 154)  # x,y,width,height relative to guest viewport
VISIBLE_PIXELS = VIEW_W * VIEW_H - HUD_MASK[2] * HUD_MASK[3]
MAX_FILE_BYTES = 32 * 1024 * 1024


def _load_image(path, expected_size):
    path = Path(path)
    if not path.is_file() or not (32 <= path.stat().st_size <= MAX_FILE_BYTES):
        raise ValueError(f"missing/invalid/oversized image: {path}")
    with Image.open(path) as image:
        image.load()
        if image.size != expected_size:
            raise ValueError(f"unexpected image size: {path} {image.size}")
        return image.convert("RGB")


def compare_scene(reference_png, screenshot_png):
    source = _load_image(reference_png, (WIDTH, HEIGHT))
    desktop = _load_image(screenshot_png, SCREEN_SIZE)
    # Fixed exact layout measured in the Stage-289 NeXium Xvfb session.
    expected = source.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST)
    observed = desktop.crop((VIEW_X, 0, VIEW_X + VIEW_W, VIEW_H))

    x, y, w, h = HUD_MASK
    area = (x, y, x + w - 1, y + h - 1)
    ImageDraw.Draw(expected).rectangle(area, fill=(0, 0, 0))
    ImageDraw.Draw(observed).rectangle(area, fill=(0, 0, 0))
    difference = ImageChops.difference(expected, observed)
    channels = difference.split()
    maximum = ImageChops.lighter(
        ImageChops.lighter(channels[0], channels[1]), channels[2])
    histogram = maximum.histogram()
    mismatches = sum(histogram[1:])
    worst_delta = max((i for i, n in enumerate(histogram) if n), default=0)
    return {
        "scene": Path(reference_png).stem,
        "reference_sha256": hashlib.sha256(Path(reference_png).read_bytes()).hexdigest(),
        "observed_sha256": hashlib.sha256(Path(screenshot_png).read_bytes()).hexdigest(),
        "visible_pixels_compared": VISIBLE_PIXELS,
        "hud_pixels_excluded": HUD_MASK[2] * HUD_MASK[3],
        "mismatched_visible_pixels": mismatches,
        "maximum_channel_delta": worst_delta,
        "exact_visible_rgb_match": mismatches == 0,
        "masked_projected_reference_rgb_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
        "masked_observed_rgb_sha256": hashlib.sha256(observed.tobytes()).hexdigest(),
    }


def audit_all(reference_dir, observed_dir, report_path):
    reference_dir, observed_dir = Path(reference_dir), Path(observed_dir)
    if reference_dir.resolve() == observed_dir.resolve():
        raise ValueError("observed screenshots must not alias host references")
    # Existing same-commit reference verifier checks all five PNG+RGB
    # checksums and the expected scene geometry before pixel projection.
    load_references(reference_dir)
    expected = {n + ".png" for n in NAMES}
    found = {p.name for p in observed_dir.glob("*.png")}
    if found != expected:
        raise ValueError(f"expected exactly five named screenshots: {sorted(found)}")
    scenes = [compare_scene(reference_dir / (n + ".png"),
                            observed_dir / (n + ".png")) for n in NAMES]
    complete = all(item["exact_visible_rgb_match"] for item in scenes)
    report = {
        "kind": "nexium_five_checkpoint_projected_rgb_parity",
        "comparison": "exact_rgb_in_visible_nearest_neighbor_projected_region",
        "native_1280x720_gpu_framebuffer_captured": False,
        "ne_xium_screenshot_origin": "ci_xvfb_observation_not_hardware_attestation",
        "host_reference_kind": "host_reference_not_emulator_capture",
        "guest_rectangle_desktop": [VIEW_X, 0, VIEW_W, VIEW_H],
        "guest_overlay_mask_relative": list(HUD_MASK),
        "reference_resolution": [WIDTH, HEIGHT],
        "observed_desktop_resolution": list(SCREEN_SIZE),
        "verified_scene_names": list(NAMES),
        "visible_pixels_compared_total": sum(x["visible_pixels_compared"] for x in scenes),
        "hud_pixels_excluded_total": sum(x["hud_pixels_excluded"] for x in scenes),
        "mismatched_visible_pixels_total": sum(x["mismatched_visible_pixels"] for x in scenes),
        "all_five_projected_visible_rgb_match": complete,
        "scenes": scenes,
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_all(args.reference, args.observed, args.report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Projected RGB parity audit rejected: {exc}\n")
    print(json.dumps({
        "all_five_projected_visible_rgb_match":
            result["all_five_projected_visible_rgb_match"],
        "pixels_compared": result["visible_pixels_compared_total"],
        "mismatched_pixels": result["mismatched_visible_pixels_total"],
    }, sort_keys=True))
    if not result["all_five_projected_visible_rgb_match"]:
        parser.exit(1, "The game-field pixels diverged from host references\n")


if __name__ == "__main__":
    main()
