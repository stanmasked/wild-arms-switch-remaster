#!/usr/bin/env python3
"""Validate reproducible synthetic field captures; emit PNG reference frames.

These are host-rendered scenes, never emulator screenshots.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import zlib

NAMES = (
    "00_area0_start",
    "01_area0_event",
    "02_area0_exit",
    "03_area1_start",
    "04_area0_return",
)
WIDTH = 1280
HEIGHT = 720
EXPECTED_BARS = (
    (63, 191, 138),
    (246, 183, 66),
    (246, 183, 66),
    (105, 160, 230),
    (63, 191, 138),
)
EXPECTED_BACKGROUNDS = (
    (14, 20, 34),
    (14, 20, 34),
    (14, 20, 34),
    (19, 34, 38),
    (14, 20, 34),
)


def read_ppm(path: pathlib.Path) -> bytes:
    content = path.read_bytes()
    magic = f"P6\n{WIDTH} {HEIGHT}\n255\n".encode("ascii")
    if not content.startswith(magic):
        raise ValueError(f"unexpected PPM header: {path}")
    rgb = content[len(magic):]
    if len(rgb) != WIDTH * HEIGHT * 3:
        raise ValueError(f"unexpected PPM payload length: {path}")
    return rgb


def pixel(rgb: bytes, x: int, y: int) -> tuple[int, int, int]:
    start = (y * WIDTH + x) * 3
    return tuple(rgb[start:start + 3])


def png_chunk(kind: bytes, content: bytes) -> bytes:
    return (
        struct.pack(">I", len(content))
        + kind + content
        + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)
    )


def make_png(rgb: bytes) -> bytes:
    row_bytes = WIDTH * 3
    scanlines = bytearray()
    for y in range(HEIGHT):
        scanlines.append(0)
        scanlines.extend(rgb[y * row_bytes:(y + 1) * row_bytes])
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9))
        + png_chunk(b"IEND", b"")
    )


def run(first: pathlib.Path, second: pathlib.Path, output: pathlib.Path) -> None:
    required = {name + ".ppm" for name in NAMES}
    for folder in (first, second):
        available = {x.name for x in folder.iterdir() if x.is_file()}
        if available != required:
            raise ValueError(f"unexpected capture set in {folder}: {sorted(available)}")

    output.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "host_reference_not_emulator_capture",
                "width": WIDTH, "height": HEIGHT, "frames": []}
    checksums = []
    for index, name in enumerate(NAMES):
        rgb_a = read_ppm(first / (name + ".ppm"))
        rgb_b = read_ppm(second / (name + ".ppm"))
        if rgb_a != rgb_b:
            raise ValueError(f"non-deterministic replay: {name}")
        if pixel(rgb_a, 0, 0) != EXPECTED_BARS[index]:
            raise ValueError(f"wrong status bar pixel: {name}")
        if pixel(rgb_a, 0, 100) != EXPECTED_BACKGROUNDS[index]:
            raise ValueError(f"wrong background pixel: {name}")

        raw_sha256 = hashlib.sha256(rgb_a).hexdigest()
        checksums.append(raw_sha256)
        png_data = make_png(rgb_a)
        (output / (name + ".png")).write_bytes(png_data)
        manifest["frames"].append({
            "scene": name,
            "raw_rgb_sha256": raw_sha256,
            "png_sha256": hashlib.sha256(png_data).hexdigest(),
            "status_rgb": list(EXPECTED_BARS[index]),
        })
    if len(set(checksums)) != len(NAMES):
        raise ValueError("capture frames must differ across gameplay states")
    (output / "capture_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Verified 5 deterministic synthetic frames and exported PNG references")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=pathlib.Path)
    parser.add_argument("second", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    run(args.first, args.second, args.output)


if __name__ == "__main__":
    main()
