#!/usr/bin/env python3
"""Validate the Nintendo Switch homebrew NRO0 container, without executing it.

Format: switchbrew/libnx nro.h. This validates structure, not emulator support.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

NRO_START = 0x10
NRO_HEADER_END = 0x80
ASSET_HEADER_LEN = 0x38
MAX_NRO_BYTES = 64 * 1024 * 1024
SEGMENT_NAMES = ("text", "rodata", "data")
ASSET_NAMES = ("icon", "nacp", "romfs")


class NroFormatError(ValueError):
    pass


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def read_nro(path):
    path = Path(path)
    if not path.is_file() or not (NRO_HEADER_END <= path.stat().st_size <= MAX_NRO_BYTES):
        raise NroFormatError("missing NRO or unsupported file size")
    data = path.read_bytes()
    if data[NRO_START:NRO_START + 4] != b"NRO0":
        raise NroFormatError("missing NRO0 signature at offset 0x10")
    version = _u32(data, 0x14)
    declared_size = _u32(data, 0x18)
    flags = _u32(data, 0x1C)
    mod_offset = _u32(data, 0x04)
    bss_size = _u32(data, 0x38)
    if declared_size < NRO_HEADER_END or declared_size > len(data):
        raise NroFormatError("declared NRO image exceeds or underflows file")
    if mod_offset != 0 and not (NRO_HEADER_END <= mod_offset < declared_size):
        raise NroFormatError("MOD0 offset lies outside executable image")
    if version != 0:
        raise NroFormatError("unknown NRO header version")
    if flags & ~1:
        raise NroFormatError("unsupported NRO header flags")

    segments = []
    last_end = 0
    for i, name in enumerate(SEGMENT_NAMES):
        offset = _u32(data, 0x20 + 8 * i)
        size = _u32(data, 0x24 + 8 * i)
        if size == 0:
            if name == "text":
                raise NroFormatError("executable text segment is empty")
            if offset > declared_size:
                raise NroFormatError(f"empty {name} segment is outside image")
        else:
            # elf2nro normally places .text at offset 0, so its file image
            # contains the NroStart/NroHeader region overlaid by the tool.
            # Other segments must follow the end of the previous segment.
            if name == "text" and offset not in (0,) and offset < NRO_HEADER_END:
                raise NroFormatError("text segment starts inside NRO header")
            if offset < last_end or offset + size > declared_size:
                raise NroFormatError(f"{name} segment is overlapping or out of bounds")
            if offset % 4:
                raise NroFormatError(f"{name} segment offset is not aligned")
            last_end = offset + size
        segments.append({"name": name, "offset": offset, "size": size})

    asset_info = None
    if len(data) > declared_size:
        remaining = data[declared_size:]
        if len(remaining) < ASSET_HEADER_LEN:
            raise NroFormatError("trailing data is too short for an ASET header")
        if remaining[0:4] != b"ASET" or _u32(remaining, 4) != 0:
            raise NroFormatError("invalid or unsupported ASET trailer")
        sections = []
        occupied = []
        for i, name in enumerate(ASSET_NAMES):
            offset, size = struct.unpack_from("<QQ", remaining, 8 + i * 16)
            if size:
                if offset < ASSET_HEADER_LEN or offset + size > len(remaining):
                    raise NroFormatError(f"{name} asset is out of bounds")
                occupied.append((offset, offset + size, name))
            elif offset > len(remaining):
                raise NroFormatError(f"empty {name} asset has invalid offset")
            sections.append({"name": name, "offset": offset, "size": size})
        for previous, current in zip(sorted(occupied), sorted(occupied)[1:]):
            if previous[1] > current[0]:
                raise NroFormatError("overlapping ASET data sections")
        asset_info = {"header_offset": declared_size, "sections": sections}

    return {
        "format": "NRO0",
        "validation": "static_container_only_not_executed",
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": version,
        "flags": flags,
        "mod_offset": mod_offset,
        "image_size": declared_size,
        "bss_size": bss_size,
        "build_id_hex": data[0x40:0x60].hex(),
        "segments": segments,
        "assets": asset_info,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nro", type=Path)
    parser.add_argument("--json", type=Path, help="write deterministic JSON audit")
    args = parser.parse_args()
    try:
        manifest = read_nro(args.nro)
    except (OSError, NroFormatError) as exc:
        parser.exit(1, f"NRO container rejected: {exc}\n")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(json.dumps({
        "format": manifest["format"],
        "image_size": manifest["image_size"],
        "file_size": manifest["file_size"],
        "sha256": manifest["sha256"],
        "asset_header": manifest["assets"] is not None
    }, sort_keys=True))


if __name__ == "__main__":
    main()
