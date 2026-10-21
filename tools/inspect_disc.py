#!/usr/bin/env python3
"""Read-only ISO9660 inventory for raw 2352-byte PS1 MODE2/Form1 images.

Only directory metadata is reported. Proprietary containers and assets are not
decoded or exported; unsupported layouts fail closed.
"""
import argparse
import json

SECTOR_BYTES = 2352
LOGICAL_BLOCK_BYTES = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MAX_DIRECTORY_BYTES = 64 * 1024 * 1024


def _both_endian(buf, offset, width, label):
    end = offset + 2 * width
    if offset < 0 or end > len(buf):
        raise ValueError(f"truncated ISO9660 {label} field")
    little = int.from_bytes(buf[offset:offset + width], "little")
    big = int.from_bytes(buf[offset + width:end], "big")
    if little != big:
        raise ValueError(f"ISO9660 {label} endian copies disagree")
    return little


def inspect(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        image_size = f.tell()
        if image_size % SECTOR_BYTES:
            raise ValueError("raw image size is not a whole number of 2352-byte sectors")
        image_sectors = image_size // SECTOR_BYTES
        if image_sectors <= 16:
            raise ValueError("raw image is too short to contain the PVD at LBA 16")
        f.seek(0)
        volume_blocks = None

        def sector(lba):
            if type(lba) is not int or lba < 0 or lba >= image_sectors:
                raise ValueError(f"sector LBA out of raw-image bounds: {lba}")
            if volume_blocks is not None and lba >= volume_blocks:
                raise ValueError(f"sector LBA outside ISO volume: {lba}")
            f.seek(lba * SECTOR_BYTES)
            raw = f.read(SECTOR_BYTES)
            if len(raw) != SECTOR_BYTES or raw[:12] != SYNC:
                raise ValueError(f"Invalid sector sync/bounds at LBA {lba}")
            if raw[15] != 2:
                raise ValueError(f"Not MODE2 at LBA {lba}")
            if raw[16:20] != raw[20:24]:
                raise ValueError(f"XA subheader copies disagree at LBA {lba}")
            if raw[18] & 0x20:
                raise ValueError(f"Not MODE2/Form1 at LBA {lba}")
            return raw[24:24 + LOGICAL_BLOCK_BYTES]

        def record(buf):
            if len(buf) < 34:
                raise ValueError("ISO9660 directory record is shorter than 34 bytes")
            record_length = buf[0]
            if record_length != len(buf) or record_length < 34:
                raise ValueError("invalid ISO9660 directory record length")
            ext_attr_length = buf[1]
            raw_lba = _both_endian(buf, 2, 4, "extent LBA")
            size = _both_endian(buf, 10, 4, "data length")
            name_length = buf[32]
            if name_length == 0:
                raise ValueError("ISO9660 directory record has an empty identifier")
            minimum = 33 + name_length + (1 if name_length % 2 == 0 else 0)
            if minimum > record_length:
                raise ValueError("ISO9660 identifier exceeds its directory record")
            if buf[26] != 0 or buf[27] != 0:
                raise ValueError("interleaved ISO9660 extents are unsupported")
            if buf[25] & 0x80:
                raise ValueError("multi-extent ISO9660 files are unsupported")
            volume_sequence = _both_endian(buf, 28, 2, "volume sequence")
            if volume_sequence == 0:
                raise ValueError("ISO9660 volume sequence must be nonzero")
            return {
                "name": buf[33:33 + name_length].decode("ascii", "replace"),
                "lba": raw_lba + ext_attr_length,
                "size": size,
                "directory": bool(buf[25] & 2),
            }

        def validate_extent(lba, size, label):
            if type(lba) is not int or type(size) is not int or lba < 0 or size < 0:
                raise ValueError(f"invalid extent for {label}")
            if volume_blocks is None:
                raise ValueError("ISO volume size has not been validated")
            if lba > volume_blocks or lba > image_sectors:
                raise ValueError(f"extent LBA outside volume for {label}")
            sectors = (size + LOGICAL_BLOCK_BYTES - 1) // LOGICAL_BLOCK_BYTES
            if lba + sectors > volume_blocks or lba + sectors > image_sectors:
                raise ValueError(f"extent exceeds ISO/raw-image bounds for {label}")

        def read_directory_extent(lba, size):
            validate_extent(lba, size, f"directory at LBA {lba}")
            if size > MAX_DIRECTORY_BYTES:
                raise ValueError(f"directory extent exceeds safety limit: {size} bytes")
            data = bytearray()
            for offset in range((size + LOGICAL_BLOCK_BYTES - 1) // LOGICAL_BLOCK_BYTES):
                data.extend(sector(lba + offset))
            return bytes(data[:size])

        pvd = sector(16)
        if pvd[0] != 1 or pvd[1:6] != b"CD001" or pvd[6] != 1:
            raise ValueError("ISO9660 primary volume descriptor not found at LBA 16")
        volume_blocks = _both_endian(pvd, 80, 4, "volume space size")
        logical_block_size = _both_endian(pvd, 128, 2, "logical block size")
        if logical_block_size != LOGICAL_BLOCK_BYTES:
            raise ValueError(f"unsupported ISO logical block size: {logical_block_size}")
        if volume_blocks <= 16 or volume_blocks > image_sectors:
            raise ValueError("ISO volume size exceeds available raw sectors or is invalid")

        root_length = pvd[156]
        if root_length < 34 or 156 + root_length > len(pvd):
            raise ValueError("invalid root directory record in primary volume descriptor")
        root = record(pvd[156:156 + root_length])
        if not root["directory"] or root["name"] != "\x00":
            raise ValueError("PVD root record is not the ISO9660 root directory")
        validate_extent(root["lba"], root["size"], "root directory")

        entries = []
        visited = set()

        def walk(directory, prefix="", depth=0):
            if depth > 20:
                raise ValueError("ISO9660 directory nesting exceeds safety limit")
            key = (directory["lba"], directory["size"])
            if key in visited:
                raise ValueError(f"repeated/cyclic ISO9660 directory extent: {key}")
            visited.add(key)
            blob = read_directory_extent(*key)
            pos = 0
            while pos < len(blob):
                record_length = blob[pos]
                if record_length == 0:
                    pos = (pos // LOGICAL_BLOCK_BYTES + 1) * LOGICAL_BLOCK_BYTES
                    continue
                if record_length > LOGICAL_BLOCK_BYTES - (pos % LOGICAL_BLOCK_BYTES):
                    raise ValueError("ISO9660 directory record crosses a logical block boundary")
                if pos + record_length > len(blob):
                    raise ValueError("truncated ISO9660 directory record")
                entry = record(blob[pos:pos + record_length])
                pos += record_length
                validate_extent(entry["lba"], entry["size"], entry["name"])
                if entry["name"] in ("\x00", "\x01"):
                    continue
                entry["path"] = prefix + "/" + entry.pop("name")
                entries.append(entry)
                if entry["directory"]:
                    walk(entry, entry["path"], depth + 1)

        walk(root)
        return {
            "volume": pvd[40:72].decode("ascii", "replace").strip(),
            "entries": entries,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = inspect(args.bin)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Volume:", result["volume"])
        for item in result["entries"]:
            print(item["path"], item["size"], item["lba"],
                  "DIR" if item["directory"] else "FILE")
