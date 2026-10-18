#!/usr/bin/env python3
"""Select five real NeXium checkpoint screenshots against same-commit host PNGs.

Scene equivalence uses status strip, 77 terrain pixels, exact sprite colour
and predicted position. It is NOT an exact full-frame comparison because
NeXium scales the 1280x720 source into a 1600x900 desktop window.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageChops
from audit_field_capture import NAMES, EXPECTED_BARS, WIDTH, HEIGHT

SCREEN_SIZE = (1600, 900)
# Observed fixed NeXium 1280x720 Vulkan view inside Xvfb desktop.
VIEW_X, VIEW_W, VIEW_H = 23, 1234, 694
GAME_ROI = (260, 130, 1000, 600)
SPRITE_CENTERS = ((384, 232), (576, 232), (704, 488),
                  (384, 232), (384, 232))
SPRITE_RED = (201, 67, 76)
SPRITE_WHITE = (246, 246, 246)
MIN_SPRITE_PIXELS = 250
MIN_TERRAIN_MATCHES = 75
TERRAIN_SAMPLES = 77
MAX_TIMELINE_FILES = 150


def screen_point(x, y):
    return (VIEW_X + round(x * VIEW_W / WIDTH),
            round(y * VIEW_H / HEIGHT))


def load_references(reference):
    reference = Path(reference)
    manifest = json.loads((reference / "capture_manifest.json").read_text())
    if (manifest.get("kind") != "host_reference_not_emulator_capture"
            or manifest.get("width") != WIDTH
            or manifest.get("height") != HEIGHT
            or manifest.get("round_trip_pixels_equal") is not True
            or [entry.get("scene") for entry in manifest.get("frames", [])]
            != list(NAMES)):
        raise ValueError("host reference manifest has wrong provenance or scenes")
    result = []
    for i, (name, entry) in enumerate(zip(NAMES, manifest["frames"])):
        path = reference / (name + ".png")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["png_sha256"]:
            raise ValueError(f"reference PNG digest mismatch: {name}")
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            if rgb.size != (WIDTH, HEIGHT):
                raise ValueError(f"reference dimensions mismatch: {name}")
            if hashlib.sha256(rgb.tobytes()).hexdigest() != entry["raw_rgb_sha256"]:
                raise ValueError(f"reference RGB digest mismatch: {name}")
            if rgb.getpixel((1100, 5)) != EXPECTED_BARS[i]:
                raise ValueError(f"reference status bar mismatch: {name}")
            sprite = SPRITE_WHITE if i in (1, 2) else SPRITE_RED
            cx, cy = SPRITE_CENTERS[i]
            if rgb.getpixel((cx - 12, cy - 12)) != sprite:
                raise ValueError(f"reference player mismatch: {name}")
            samples = tuple(rgb.getpixel((288 + col * 64 + 11,
                                           136 + row * 64 + 11))
                            for row in range(7) for col in range(11))
        result.append({
            "scene": name, "sprite": sprite, "center": screen_point(cx, cy),
            "bar": EXPECTED_BARS[i], "samples": samples,
            "reference_png_sha256": entry["png_sha256"],
        })
    if result[0]["samples"] != result[4]["samples"]:
        raise ValueError("reference initial/return terrain differs")
    return result


def inspect_frame(path, expected):
    with Image.open(path) as image:
        image.load()
        if image.size != SCREEN_SIZE:
            raise ValueError(f"wrong Xvfb dimensions: {path}")
        pixels = image.convert("RGB")
        bar_match = all(pixels.getpixel((x, 5)) == expected["bar"]
                        for x in (700, 950, 1100))
        terrain_matches = 0
        for n, value in enumerate(expected["samples"]):
            row, col = divmod(n, 11)
            point = screen_point(288 + col * 64 + 11,
                                 136 + row * 64 + 11)
            terrain_matches += pixels.getpixel(point) == value
        cx, cy = expected["center"]
        sprite_pixels = sum(
            pixels.getpixel((x, y)) == expected["sprite"]
            for y in range(cy - 14, cy + 15)
            for x in range(cx - 14, cx + 15)
        )
    valid = bar_match and (terrain_matches >= MIN_TERRAIN_MATCHES
                           and sprite_pixels >= MIN_SPRITE_PIXELS)
    return {
        "matched": valid, "status_match": bar_match,
        "terrain_matches": terrain_matches,
        "terrain_samples": TERRAIN_SAMPLES,
        "sprite_pixels": sprite_pixels
    }


def game_pixels_equal(a, b):
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != SCREEN_SIZE or ib.size != SCREEN_SIZE:
            raise ValueError("invalid screenshot dimensions")
        return ImageChops.difference(
            ia.convert("RGB").crop(GAME_ROI),
            ib.convert("RGB").crop(GAME_ROI)).getbbox() is None


def audit_sequence(reference_dir, initial, timeline_dir, report_path,
                   selected_dir=None):
    refs = load_references(reference_dir)
    initial = Path(initial)
    timeline_dir = Path(timeline_dir)
    files = sorted(timeline_dir.glob("frame-*.png"))
    if not 20 <= len(files) <= MAX_TIMELINE_FILES:
        raise ValueError("timeline must contain 20 to 150 actual screenshots")
    if len(set(p.resolve() for p in [initial, *files])) != len(files) + 1:
        raise ValueError("duplicate or aliased screenshot paths")
    first = inspect_frame(initial, refs[0])
    chosen = [{"scene": NAMES[0], "file": initial.name,
               "sha256": hashlib.sha256(initial.read_bytes()).hexdigest(),
               "validation": first}] if first["matched"] else []
    next_scene = 1
    examined = 0
    for shot in files:
        if next_scene >= len(refs):
            break
        inspected = inspect_frame(shot, refs[next_scene])
        examined += 1
        if inspected["matched"]:
            chosen.append({
                "scene": NAMES[next_scene], "file": shot.name,
                "sha256": hashlib.sha256(shot.read_bytes()).hexdigest(),
                "validation": inspected
            })
            next_scene += 1
    complete = next_scene == len(refs) and bool(chosen)
    if complete and not game_pixels_equal(initial, timeline_dir / chosen[-1]["file"]):
        complete = False
    result = {
        "kind": "nexium_same_commit_five_checkpoint_structural_comparison",
        "reference_kind": "host_reference_not_emulator_capture",
        "observed_kind": "experimental_xvfb_screenshots",
        "comparison_type": "terrain_sprite_bar_samples_not_full_rgb_parity",
        "excludes_performance_overlay": True,
        "source_dimensions": [WIDTH, HEIGHT],
        "desktop_dimensions": list(SCREEN_SIZE),
        "scene_order": list(NAMES),
        "initial_verified": first["matched"],
        "captured_frame_count": len(files),
        "frames_examined": examined,
        "verified_scenes": chosen,
        "full_five_checkpoint_sequence_observed": complete,
        "pixel_perfect_1280x720_parity_verified": False,
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    if complete and selected_dir is not None:
        selected_dir = Path(selected_dir)
        if selected_dir.exists() and any(selected_dir.iterdir()):
            raise ValueError("selected checkpoint output directory is not empty")
        selected_dir.mkdir(parents=True, exist_ok=True)
        for entry in chosen:
            source = (initial if entry["scene"] == NAMES[0] else
                      timeline_dir / entry["file"])
            shutil.copyfile(source, selected_dir / (entry["scene"] + ".png"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--selected", type=Path)
    args = parser.parse_args()
    try:
        result = audit_sequence(args.reference, args.initial, args.timeline,
                                args.report, args.selected)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Checkpoint evidence invalid: {exc}\n")
    print(json.dumps({
        "verified_scene_count": len(result["verified_scenes"]),
        "full_five_checkpoint_sequence_observed":
            result["full_five_checkpoint_sequence_observed"],
    }, sort_keys=True))
    if not result["full_five_checkpoint_sequence_observed"]:
        parser.exit(1, "Missing a verified real NeXium checkpoint\n")


if __name__ == "__main__":
    main()
