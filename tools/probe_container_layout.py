#!/usr/bin/env python3
"""Bounded, local-only statistics for candidate PS1 data containers.

The probe reads a small prefix from selected ISO9660 extents and emits only
hashes, aggregate byte statistics, sector classes and pointer-like word
positions. It never exports raw payload bytes or decodes assets.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

SECTOR_BYTES = 2352
LOGICAL_BLOCK_BYTES = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MAX_SAMPLE_BYTES = 1024 * 1024
DEFAULT_PATHS = (
    "/BIN/CDSTG.BIN;1",
    "/BIN/CDFLR.BIN;1",
    "/BIN/CDEN.BIN;1",
    "/BIN/CDGD.BIN;1",
    "/BIN/CDEF.BIN;1",
)


def _entropy(data):
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length)
                for count in counts.values())


def _word_summary(data, declared_size):
    words = [
        int.from_bytes(data[offset:offset + 4], "little")
        for offset in range(0, len(data) - 3, 4)
    ]
    pointer_offsets = [
        index * 4 for index, word in enumerate(words)
        if 0x80000000 <= word < 0x80200000
    ]
    return {
        "u32_le_word_count": len(words),
        "distinct_u32_le_word_count": len(set(words)),
        "u32_le_words_inside_declared_file_range": sum(
            0 < word < declared_size for word in words),
        "ps1_kseg0_pointer_like_word_count": len(pointer_offsets),
        "first_pointer_like_word_offsets": pointer_offsets[:16],
    }


def probe(image_path, inventory_path, paths=None, sample_bytes=4096):
    if type(sample_bytes) is not int or not 1 <= sample_bytes <= MAX_SAMPLE_BYTES:
        raise ValueError(f"sample-bytes must be between 1 and {MAX_SAMPLE_BYTES}")
    requested = tuple(path.lstrip("/") for path in (DEFAULT_PATHS if paths is None else paths))
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("candidate paths must be nonempty and unique")

    inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    entries = inventory.get("entries") if isinstance(inventory, dict) else None
    if not isinstance(entries, list):
        raise ValueError("inventory must contain an entries array")
    by_path = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("inventory entry is missing a path")
        key = entry["path"].lstrip("/")
        if key in by_path:
            raise ValueError(f"duplicate inventory path: {key}")
        by_path[key] = entry

    selected = []
    for path in requested:
        if path not in by_path:
            raise ValueError(f"candidate is absent from inventory: /{path}")
        entry = by_path[path]
        if entry.get("directory") is not False:
            raise ValueError(f"candidate is not a regular file: /{path}")
        lba, size = entry.get("lba"), entry.get("size")
        if type(lba) is not int or type(size) is not int or lba < 0 or size <= 0:
            raise ValueError(f"invalid candidate extent: /{path}")
        selected.append((path, lba, size))

    with open(image_path, "rb") as image:
        image.seek(0, 2)
        image_size = image.tell()
        if image_size % SECTOR_BYTES:
            raise ValueError("raw image size is not a whole number of 2352-byte sectors")
        image_sectors = image_size // SECTOR_BYTES
        output = []
        for path, lba, size in selected:
            allocated = (size + LOGICAL_BLOCK_BYTES - 1) // LOGICAL_BLOCK_BYTES
            if lba + allocated > image_sectors:
                raise ValueError(f"candidate extent exceeds raw image: /{path}")
            wanted = min(size, sample_bytes)
            needed_sectors = (wanted + LOGICAL_BLOCK_BYTES - 1) // LOGICAL_BLOCK_BYTES
            chunks = []
            sector_types = Counter()
            unsupported = None
            for index in range(needed_sectors):
                current_lba = lba + index
                image.seek(current_lba * SECTOR_BYTES)
                raw = image.read(SECTOR_BYTES)
                if len(raw) != SECTOR_BYTES or raw[:12] != SYNC:
                    raise ValueError(f"invalid sector sync/bounds at LBA {current_lba}")
                mode = raw[15]
                if mode != 2:
                    unsupported = "UNSUPPORTED_SECTOR_MODE"
                    sector_types[f"mode{mode}"] += 1
                    break
                if raw[16:20] != raw[20:24]:
                    raise ValueError(f"XA subheader copies disagree at LBA {current_lba}")
                if raw[18] & 0x20:
                    unsupported = "UNSUPPORTED_MODE2_FORM2"
                    sector_types["mode2_form2"] += 1
                    break
                sector_types["mode2_form1"] += 1
                chunks.append(raw[24:24 + LOGICAL_BLOCK_BYTES])

            if unsupported:
                output.append({
                    "path": "/" + path,
                    "extent_lba": lba,
                    "declared_size_bytes": size,
                    "status": unsupported,
                    "sampled_sector_count": sum(sector_types.values()),
                    "sector_types": dict(sorted(sector_types.items())),
                })
                continue

            sample = b"".join(chunks)[:wanted]
            first_nonzero = next(
                (offset for offset, value in enumerate(sample) if value), None)
            output.append({
                "path": "/" + path,
                "extent_lba": lba,
                "declared_size_bytes": size,
                "status": "SAMPLED",
                "sampled_payload_bytes": len(sample),
                "sampled_sector_count": sum(sector_types.values()),
                "sector_types": dict(sorted(sector_types.items())),
                "sample_sha256": hashlib.sha256(sample).hexdigest(),
                "entropy_bits_per_byte": round(_entropy(sample), 6),
                "zero_byte_fraction": round(sample.count(0) / len(sample), 6),
                "first_nonzero_offset": first_nonzero,
                "word_summary": _word_summary(sample, size),
            })

    return {
        "schema": 1,
        "kind": "BOUNDED_PRIVATE_CONTAINER_LAYOUT_PROBE",
        "inventory_volume": inventory.get("volume"),
        "sample_limit_bytes": sample_bytes,
        "original_payload_exported": False,
        "decoded_assets_exported": False,
        "candidates": output,
        "limitations": (
            "Aggregate metadata only. KSEG0-like words are heuristics, not proof "
            "of pointers or an archive format. MODE2/Form2 payloads are not decoded."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--sample-bytes", type=int, default=4096)
    parser.add_argument("--path", action="append", dest="paths",
                        help="candidate path from the inventory; repeat to select several")
    parser.add_argument("--report", type=Path,
                        help="write the metadata-only report to a local JSON file")
    args = parser.parse_args()
    try:
        result = probe(args.image, args.inventory, args.paths, args.sample_bytes)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"container probe rejected: {error}\n")
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
