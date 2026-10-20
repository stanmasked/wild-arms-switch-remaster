#!/usr/bin/env python3
"""Convert bounded P6 synthetic host battle screenshots into portable PNG.

No external dependencies; does not treat host renders as emulator evidence.
"""
import binascii
import struct
import sys
import zlib
from pathlib import Path

WIDTH, HEIGHT = 1280, 720
HEADER = b"P6\n1280 720\n255\n"
MAX_DATA = WIDTH * HEIGHT * 3


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF))


def convert(source):
    source = Path(source)
    payload = source.read_bytes()
    if not payload.startswith(HEADER) or len(payload) != len(HEADER) + MAX_DATA:
        raise ValueError(f"invalid bounded PPM source: {source}")
    data = payload[len(HEADER):]
    scanlines = b"".join(
        b"\x00" + data[offset:offset + WIDTH * 3]
        for offset in range(0, len(data), WIDTH * 3))
    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(scanlines, 9)) +
           chunk(b"IEND", b""))
    destination = source.with_suffix(".png")
    destination.write_bytes(png)
    print(f"{destination} bytes={len(png)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: export_battle_preview.py file.ppm [...]")
    for arg in sys.argv[1:]:
        convert(arg)
