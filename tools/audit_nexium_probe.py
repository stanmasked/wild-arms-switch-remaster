#!/usr/bin/env python3
"""Experimental pixel evidence from NeXium/Xvfb screenshots, not a game test.

A valid signature suggests that a guest-rendered synthetic framebuffer appeared
on the host desktop. It does not authenticate the emulator or game provenance.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

# Native scene palette in include/field_pixels.hpp (byte-exact Xvfb RGB).
PALETTE = {
    "wall": (47, 68, 87),
    "floor": (174, 155, 115),
    "exit": (63, 191, 138),
}
PLAYER = ((201, 67, 76), (246, 246, 246))
REQUIRED_COUNT = {"wall": 2000, "floor": 2000, "exit": 500}
MINIMUM_PLAYER_PIXELS = 120


def analyze_shot(path):
    """Return measured RGB frequencies; Pillow is used only for RGB decoding."""
    from PIL import Image
    path = Path(path)
    with Image.open(path) as image:
        image.load()
        if image.width < 640 or image.height < 480:
            raise ValueError("desktop screenshot is too small")
        if image.width > 4096 or image.height > 4096:
            raise ValueError("desktop screenshot exceeds safety bounds")
        rgb = image.convert("RGB")
        counts = Counter(rgb.getdata())
        dimensions = [rgb.width, rgb.height]
    colours = {name: counts.get(value, 0) for name, value in PALETTE.items()}
    player_count = max(counts.get(value, 0) for value in PLAYER)
    valid = (all(colours[key] >= threshold for key, threshold
                 in REQUIRED_COUNT.items())
             and player_count >= MINIMUM_PLAYER_PIXELS)
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dimensions": dimensions,
        "palette_counts": colours,
        "player_pixel_count": player_count,
        "synthetic_field_signature_detected": valid,
    }


def generate_report(shots, source_commit, nexium_digest, output):
    if len(source_commit) != 40 or not all(c in "0123456789abcdef"
                                           for c in source_commit):
        raise ValueError("invalid source commit")
    if len(nexium_digest) != 64 or not all(c in "0123456789abcdef"
                                          for c in nexium_digest):
        raise ValueError("invalid emulator archive SHA-256")
    frames = []
    for filename in shots:
        path = Path(filename)
        if not path.is_file():
            continue
        frames.append(analyze_shot(path))
    detected = any(row["synthetic_field_signature_detected"]
                   for row in frames)
    report = {
        "kind": "experimental_nexium_xvfb_guest_pixel_probe",
        "source_commit": source_commit,
        "emulator_archive_sha256": nexium_digest,
        "status": ("screen_contains_expected_field_palette" if detected else
                   "runtime_not_confirmed"),
        "provenance": "ci_screen_evidence_not_device_attestation",
        "emulator_runtime_confirmed": detected,
        "screenshots": frames,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshots", nargs="*", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--nexium-archive-sha256", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = generate_report(args.screenshots, args.commit,
                                 args.nexium_archive_sha256, args.report)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"Probe invalid: {exc}\n")
    print(json.dumps({"status": result["status"],
                      "screenshots": len(result["screenshots"])},
                     sort_keys=True))
    if not result["emulator_runtime_confirmed"]:
        parser.exit(1, "No visible guest framebuffer established\n")


if __name__ == "__main__":
    main()
