#!/usr/bin/env python3
"""Metadata-only cross-slot audit of CDFLR candidate palette/data families.

Repeated byte patterns are not proof of game asset purpose. The original data
are never printed or exported; only sizes, hashes and simple counts are used.
"""
import argparse
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path

SLOT_BYTES = 0x3A000
TABLE_BYTES = 256
POINTER_COUNT = 58
PALETTES = tuple(range(42, 57, 2))
REGIONS = tuple(range(42, 58))
MAX_SLOTS = 1024
MAX_SLOT_BYTES = 4 * 1024 * 1024


def audit_regions(path, slot_bytes=SLOT_BYTES):
    path = Path(path)
    if (type(slot_bytes) is not int or slot_bytes < TABLE_BYTES + 4 or
            slot_bytes > MAX_SLOT_BYTES or slot_bytes % 4):
        raise ValueError("invalid aligned slot byte count")
    size = path.stat().st_size
    if size <= 0 or size % slot_bytes:
        raise ValueError("file size is not a whole number of slots")
    count = size // slot_bytes
    if count > MAX_SLOTS:
        raise ValueError("too many resource slots for bounded audit")

    regions = {index: [] for index in REGIONS}
    zero_trailer_slots = []
    with path.open("rb") as source:
        for slot in range(count):
            block = source.read(slot_bytes)
            if len(block) != slot_bytes:
                raise ValueError("short read from CDFLR source")
            words = struct.unpack_from("<64I", block)
            base = words[0] - TABLE_BYTES
            if not 0x80000000 <= base < 0x80200000 or base % 4:
                raise ValueError(f"slot {slot}: implausible RAM base")
            if any(word % 4 or not 0x80000000 <= word < 0x80200000
                   for word in words[:POINTER_COUNT]):
                raise ValueError(f"slot {slot}: invalid candidate pointer table")
            # 58 pointer words occupy 232 bytes, followed by an opaque
            # 24-byte trailer (nonzero in 66 of 67 original slots).
            trailer = block[POINTER_COUNT * 4:TABLE_BYTES]
            if not any(trailer):
                zero_trailer_slots.append(slot)
            offsets = [word - base for word in words[:POINTER_COUNT]]
            if (offsets[0] != TABLE_BYTES or offsets[-1] + 4 > slot_bytes or
                    any(b <= a for a, b in zip(offsets, offsets[1:]))):
                raise ValueError(f"slot {slot}: candidate pointers outside bounds or not increasing")
            for index in REGIONS:
                start = offsets[index]
                end = offsets[index + 1] if index < POINTER_COUNT - 1 else slot_bytes
                data = block[start:end]
                item = {"slot": slot, "span_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()}
                if index in PALETTES:
                    if len(data) % 2:
                        raise ValueError(f"slot {slot}: odd-sized u16 candidate region")
                    colors = struct.unpack("<" + str(len(data)//2) + "H", data)
                    item.update({
                        "u16_count": len(colors),
                        "distinct_u16_count": len(set(colors)),
                        "zero_u16_count": sum(v == 0 for v in colors),
                        "bit15_set_count": sum(bool(v & 0x8000) for v in colors),
                    })
                else:
                    item["first_word_0x8000"] = (len(data) >= 4 and
                                                  struct.unpack_from("<I", data)[0] == 0x8000)
                regions[index].append(item)

    families = []
    for index in REGIONS:
        entries = regions[index]
        groups = defaultdict(list)
        for item in entries:
            groups[item["sha256"]].append(item["slot"])
        sizes = [item["span_bytes"] for item in entries]
        row = {
            "pointer_index": index,
            "kind_hypothesis": ("u16_palette_sized_data" if index in PALETTES else "paired_data"),
            "unique_content_hash_count": len(groups),
            "identical_across_all_slots": len(groups) == 1,
            "largest_identical_group_size": max(map(len, groups.values())),
            "distinct_region_lengths": sorted(set(sizes)),
            "min_span_bytes": min(sizes),
            "max_span_bytes": max(sizes),
            "slot0_region_sha256": entries[0]["sha256"],
        }
        if index in PALETTES:
            for key in ("u16_count", "distinct_u16_count", "zero_u16_count", "bit15_set_count"):
                vals = [x[key] for x in entries]
                row[key + "_range"] = [min(vals), max(vals)]
            row["non512_slot_indices"] = [
                item["slot"] for item in entries if item["span_bytes"] != 512]
        else:
            row["first_word_0x8000_count"] = sum(x["first_word_0x8000"] for x in entries)
            row["last_region_extent_is_upper_bound_only"] = index == 57
        families.append(row)
    return {
        "schema": 1,
        "kind": "PRIVATE_CDFLR_REGION_FAMILY_AUDIT",
        "source_name": path.name,
        "source_size_bytes": size,
        "slot_bytes": slot_bytes,
        "slot_count": count,
        "zero_opaque_header_trailer_slots": zero_trailer_slots,
        "invariant_candidate_palette_indices": [
            f["pointer_index"] for f in families if
            f["pointer_index"] in PALETTES and f["identical_across_all_slots"]],
        "invariant_paired_data_indices": [
            f["pointer_index"] for f in families if
            f["pointer_index"] not in PALETTES and f["identical_across_all_slots"]],
        "families": families,
        "interpretation": {
            "shared_bytes_not_proof_of_shared_gameplay_purpose": True,
            "u16_color_like_words_not_verified_ps1_clut": True,
            "bit15_counts_not_verified_transparency": True,
            "last_region_size_is_upper_bound_only": True,
            "original_payload_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource", type=Path, help="private CDFLR.BIN")
    parser.add_argument("--slot-bytes", type=lambda text: int(text, 0),
                        default=SLOT_BYTES)
    args = parser.parse_args()
    print(json.dumps(audit_regions(args.resource, args.slot_bytes),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
