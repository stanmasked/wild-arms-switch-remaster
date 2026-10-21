#!/usr/bin/env python3
"""Privately convert owner-provided 256x256 indexed PNG to WAIC v1.

Only the owner-held PNG is accepted. Output is NEVER included in public CI.
WAIC is our own inspection/interop format, not a verified original PS1 file.
"""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import zlib

SIDE = 256
PALETTE_COUNT = 16
INDEX_BYTES = SIDE * SIDE
PALETTE_BYTES = 4 * PALETTE_COUNT
HEADER_BYTES = 24
TOTAL_BYTES = HEADER_BYTES + PALETTE_BYTES + INDEX_BYTES


def encode_icon(indices, rgb_palette):
    """Build a portable opaque indexed preview blob without Pillow."""
    if not isinstance(indices, (bytes, bytearray)) or len(indices) != INDEX_BYTES:
        raise ValueError("indices must be exactly 65536 bytes")
    if any(i >= PALETTE_COUNT for i in indices):
        raise ValueError("all palette indices must fit in 4 bits")
    if (not isinstance(rgb_palette, (bytes, bytearray)) or
            len(rgb_palette) != PALETTE_COUNT * 3):
        raise ValueError("RGB palette must contain exactly 16 RGB triplets")
    colors = bytearray()
    for i in range(PALETTE_COUNT):
        colors.extend(rgb_palette[i * 3:i * 3 + 3])
        colors.append(255)  # v1: opaque inspection; no PS1 STP interpretation
    payload = bytes(colors) + bytes(indices)
    crc32 = zlib.crc32(payload) & 0xFFFFFFFF
    header = struct.pack("<4sIHHHHII", b"WAIC", 1, SIDE, SIDE,
                         PALETTE_COUNT, 0, len(payload), crc32)
    assert len(header) == HEADER_BYTES
    return header + payload


def convert_private_png(source, destination):
    # Pillow is an opt-in dependency for local user-owned PNGs only.
    from PIL import Image
    source = Path(source)
    destination = Path(destination)
    if not destination.parent.is_dir():
        raise ValueError("output directory must already exist")
    with Image.open(source) as image:
        if image.mode != "P" or image.size != (SIDE, SIDE):
            raise ValueError("requires unscaled 256x256 palette-indexed PNG")
        if "transparency" in image.info:
            raise ValueError("PNG alpha is not supported by opaque WAIC v1")
        palette = image.getpalette()
        if palette is None or len(palette) < PALETTE_COUNT * 3:
            raise ValueError("missing 16-color source palette")
        if image.palette.mode != "RGB":
            raise ValueError("source PNG palette must use RGB values")
        indices = image.tobytes()
        # P-mode PNG palettes can include unused entries. Only the first 16
        # indices/colors are relevant to a raw PS1 4bpp icon sheet.
        content = encode_icon(indices, bytes(palette[:PALETTE_COUNT * 3]))
    # Exclusive create protects private files from accidental overwrites.
    with destination.open("xb") as output:
        output.write(content)
    return {
        "source_name": source.name,
        "output_name": destination.name,
        "format": "WAIC v1 opaque preview",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "has_ps1_transparency_semantics": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_png", type=Path)
    parser.add_argument("private_waic", type=Path)
    args = parser.parse_args()
    print(convert_private_png(args.private_png, args.private_waic))


if __name__ == "__main__":
    main()
