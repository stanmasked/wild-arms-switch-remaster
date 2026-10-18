#!/usr/bin/env python3
"""Compare operator-supplied PNGs to host reference frames.

This tool validates pixel correspondence. It cannot prove image provenance
or that an emulator/device was actually run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from audit_field_capture import NAMES, WIDTH, HEIGHT, make_png

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_png_rgb(path: Path, expected_size=None):
    data = path.read_bytes()
    if len(data) > 32 * 1024 * 1024 or not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"invalid or oversized PNG: {path}")
    position = len(PNG_SIGNATURE)
    size = None
    compressed = bytearray()
    saw_end = False
    chunks = 0
    while position < len(data):
        chunks += 1
        if chunks > 256 or position + 12 > len(data):
            raise ValueError(f"invalid PNG chunk layout: {path}")
        count = struct.unpack_from(">I", data, position)[0]
        position += 4
        kind = data[position:position + 4]
        position += 4
        if len(kind) != 4 or count > 32 * 1024 * 1024 or position + count + 4 > len(data):
            raise ValueError(f"truncated PNG chunk: {path}")
        payload = data[position:position + count]
        position += count
        crc = struct.unpack_from(">I", data, position)[0]
        position += 4
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError(f"PNG CRC mismatch: {path}")
        if kind == b"IHDR":
            if size is not None or count != 13 or chunks != 1:
                raise ValueError(f"invalid PNG header: {path}")
            width, height, depth, color, comp, filt, interlace = struct.unpack(
                ">IIBBBBB", payload)
            if (width == 0 or height == 0 or width > 4096 or height > 4096 or
                    depth != 8 or color not in (2, 6) or
                    comp != 0 or filt != 0 or interlace != 0):
                raise ValueError(f"unsupported PNG mode or dimensions: {path}")
            size = (width, height, 3 if color == 2 else 4)
        elif kind == b"IDAT":
            if size is None:
                raise ValueError(f"PNG data before header: {path}")
            compressed.extend(payload)
        elif kind == b"IEND":
            if count != 0 or not compressed or position != len(data):
                raise ValueError(f"invalid PNG ending: {path}")
            saw_end = True
            break
        elif kind[:1].isupper() or kind == b"tRNS":
            raise ValueError(f"unsupported PNG critical/transparency chunk: {path}")
    if not saw_end or size is None:
        raise ValueError(f"missing PNG image or IEND: {path}")
    width, height, channels = size
    if expected_size is not None and (width, height) != tuple(expected_size):
        raise ValueError(f"wrong PNG dimensions: {path}")
    scanline_bytes = width * channels
    expected = (scanline_bytes + 1) * height
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(bytes(compressed), expected + 1)
        if (len(raw) != expected or not decoder.eof or
                decoder.unconsumed_tail or decoder.unused_data):
            raise ValueError(f"wrong PNG decompressed length: {path}")
    except zlib.error as exc:
        raise ValueError(f"invalid PNG zlib stream: {path}") from exc

    out = bytearray(width * height * 3)
    previous = bytearray(scanline_bytes)
    source = 0
    destination = 0
    for _ in range(height):
        mode = raw[source]
        source += 1
        if mode > 4:
            raise ValueError(f"unsupported PNG row filter: {path}")
        row = bytearray(raw[source:source + scanline_bytes])
        source += scanline_bytes
        for offset in range(scanline_bytes):
            left = row[offset - channels] if offset >= channels else 0
            above = previous[offset]
            upper_left = previous[offset - channels] if offset >= channels else 0
            if mode == 0:
                predictor = 0
            elif mode == 1:
                predictor = left
            elif mode == 2:
                predictor = above
            elif mode == 3:
                predictor = (left + above) // 2
            else:
                guess = left + above - upper_left
                distances = (
                    abs(guess - left), abs(guess - above), abs(guess - upper_left))
                predictor = (left, above, upper_left)[distances.index(min(distances))]
            row[offset] = (row[offset] + predictor) & 255
        for pixel in range(width):
            start = pixel * channels
            out[destination:destination + 3] = row[start:start + 3]
            destination += 3
        previous = row
    return width, height, bytes(out)


def pixel_differences(reference: bytes, observed: bytes, tolerance: int):
    if len(reference) != len(observed) or len(reference) % 3:
        raise ValueError("RGB buffer lengths differ")
    mismatches = 0
    max_delta = 0
    marker = bytearray(len(reference))
    for offset in range(0, len(reference), 3):
        delta = max(abs(reference[offset + c] - observed[offset + c])
                    for c in range(3))
        if delta > max_delta:
            max_delta = delta
        if delta > tolerance:
            mismatches += 1
            marker[offset:offset + 3] = b"\xff\x00\x00"
    return mismatches, max_delta, bytes(marker)


def compare_capture(reference_dir: Path, observed_dir: Path, manifest_path: Path,
                    report_path: Path, max_channel_delta=0,
                    max_changed_pixels=0, expected_size=(WIDTH, HEIGHT),
                    write_diffs=False, capture_label="unverified_operator_input"):
    reference_dir = Path(reference_dir)
    observed_dir = Path(observed_dir)
    if reference_dir.resolve() == observed_dir.resolve():
        raise ValueError("observed directory must differ from reference directory")
    if not (0 <= max_channel_delta <= 255 and max_changed_pixels >= 0):
        raise ValueError("invalid comparison tolerance")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    names = list(NAMES)
    if (manifest.get("kind") != "host_reference_not_emulator_capture" or
            manifest.get("width") != expected_size[0] or
            manifest.get("height") != expected_size[1] or
            [x.get("scene") for x in manifest.get("frames", [])] != names or
            manifest.get("round_trip_pixels_equal") is not True):
        raise ValueError("reference manifest is missing or incompatible")
    expected_files = {name + ".png" for name in names}
    for folder in (reference_dir, observed_dir):
        if {p.name for p in folder.glob("*.png")} != expected_files:
            raise ValueError(f"expected five precisely named PNGs in {folder}")

    frames = []
    overall_passed = True
    diff_images = {}
    for scene, item in zip(names, manifest["frames"]):
        ref_path = reference_dir / (scene + ".png")
        obs_path = observed_dir / (scene + ".png")
        reference_bytes = ref_path.read_bytes()
        if hashlib.sha256(reference_bytes).hexdigest() != item["png_sha256"]:
            raise ValueError(f"reference PNG digest mismatch: {scene}")
        _, _, ref_rgb = read_png_rgb(ref_path, expected_size)
        if hashlib.sha256(ref_rgb).hexdigest() != item["raw_rgb_sha256"]:
            raise ValueError(f"reference raw RGB digest mismatch: {scene}")
        _, _, obs_rgb = read_png_rgb(obs_path, expected_size)
        mismatch, largest_delta, marked = pixel_differences(
            ref_rgb, obs_rgb, max_channel_delta)
        within_limit = mismatch <= max_changed_pixels
        overall_passed = overall_passed and within_limit
        frames.append({
            "scene": scene,
            "changed_pixels": mismatch,
            "max_absolute_channel_delta": largest_delta,
            "within_tolerance": within_limit,
            "observed_png_sha256": hashlib.sha256(obs_path.read_bytes()).hexdigest(),
        })
        if write_diffs:
            diff_images[scene] = marked

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "result": "pass" if overall_passed else "mismatch",
        "observed_capture_provenance": "not_verified_by_this_tool",
        "operator_capture_label": capture_label,
        "max_channel_delta": max_channel_delta,
        "max_changed_pixels": max_changed_pixels,
        "width": expected_size[0],
        "height": expected_size[1],
        "frames": frames,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    if write_diffs:
        if tuple(expected_size) != (WIDTH, HEIGHT):
            raise ValueError("PNG diff export requires full reference dimensions")
        diff_dir = report_path.parent / "pixel-diffs"
        diff_dir.mkdir(exist_ok=True)
        for name, rgb in diff_images.items():
            (diff_dir / (name + ".png")).write_bytes(make_png(rgb))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-channel-delta", type=int, default=0)
    parser.add_argument("--max-changed-pixels", type=int, default=0)
    parser.add_argument("--capture-label", default="unverified_operator_input")
    parser.add_argument("--write-diffs", action="store_true")
    args = parser.parse_args()
    try:
        report = compare_capture(
            args.reference, args.observed, args.manifest, args.report,
            max_channel_delta=args.max_channel_delta,
            max_changed_pixels=args.max_changed_pixels,
            write_diffs=args.write_diffs,
            capture_label=args.capture_label)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Capture comparison rejected: {exc}\n")
    print(json.dumps({"result": report["result"], "frames": report["frames"]}))
    if report["result"] != "pass":
        parser.exit(1, "PNG captures differ; inspect report and pixel-diffs\n")


if __name__ == "__main__":
    main()
