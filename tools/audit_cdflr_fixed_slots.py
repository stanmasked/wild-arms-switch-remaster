#!/usr/bin/env python3
"""Audit every fixed-size record in a PRIVATE original Wild Arms CDFLR.BIN.

Reports only metadata, hashes and counts. Does not print source contents,
decode copyrighted assets, or assume candidate palettes are proven images.
"""
import argparse
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path

DEFAULT_SLOT_BYTES = 0x3A000
POINTER_PREFIX_BYTES = 0x100
POINTER_COUNT = 58
LOW_RAM = 0x80000000
HIGH_RAM = 0x80200000
PALETTE_INDICES = tuple(range(42, 57, 2))
MAX_SLOT_BYTES = 4 * 1024 * 1024
MAX_SLOTS = 1024


def audit_fixed_slots(path, slot_bytes=DEFAULT_SLOT_BYTES):
    path = Path(path)
    if (type(slot_bytes) is not int or slot_bytes < POINTER_PREFIX_BYTES + 4
            or slot_bytes % 4 or slot_bytes > MAX_SLOT_BYTES):
        raise ValueError("slot_bytes outside bounded, aligned geometry")
    size = path.stat().st_size
    if size == 0 or size % slot_bytes:
        raise ValueError("file is not a whole number of fixed-length slots")
    count = size // slot_bytes
    if count > MAX_SLOTS:
        raise ValueError("too many slots for bounded audit")
    slots = []
    duplicates = defaultdict(list)
    all_base_candidates = set()
    with path.open("rb") as source:
        for index in range(count):
            payload = source.read(slot_bytes)
            if len(payload) != slot_bytes:
                raise ValueError("short read during fixed-slot scan")
            (first,) = struct.unpack_from("<I", payload, 0)
            base = first - POINTER_PREFIX_BYTES
            if base not in range(LOW_RAM, HIGH_RAM) or base % 4:
                raise ValueError(f"slot {index}: candidate RAM base invalid")
            pointers = struct.unpack_from("<64I", payload, 0)
            if any(p < LOW_RAM or p >= HIGH_RAM or p % 4
                   for p in pointers[:POINTER_COUNT]):
                raise ValueError(f"slot {index}: pointer outside PS1 KSEG0 RAM range")
            if (pointers[POINTER_COUNT] != 0 or
                    any(payload[(POINTER_COUNT + 1) * 4:POINTER_PREFIX_BYTES])):
                raise ValueError(f"slot {index}: missing terminator/zero padding")
            offsets = [p - base for p in pointers[:POINTER_COUNT]]
            if offsets[0] != POINTER_PREFIX_BYTES:
                raise ValueError(f"slot {index}: first pointer not after table")
            if (any(a >= b for a, b in zip(offsets, offsets[1:])) or
                    offsets[-1] + 4 > slot_bytes):
                raise ValueError(f"slot {index}: pointer order/bounds invalid")
            tags = [struct.unpack_from("<I", payload, offset)[0]
                    for offset in offsets]
            tag_41_count = sum(tags[i] == 0x41 for i in range(2, 41))
            rule_matches = 0
            for j in range(2, 41):
                start, end = offsets[j:j + 2]
                if start + 20 <= end:
                    kind, zero, one, length_field, count_field = struct.unpack_from(
                        "<5I", payload, start)
                    if (kind, zero, one) == (0x41, 0, 1) and (
                            end - start == length_field + 8 * count_field + 12):
                        rule_matches += 1
            palette_sized = []
            data_marker_count = 0
            for j in PALETTE_INDICES:
                palette_sized.append(offsets[j + 1] - offsets[j] == 512)
                if tags[j + 1] == 0x8000:
                    data_marker_count += 1
            digest = hashlib.sha256(payload).hexdigest()
            duplicates[digest].append(index)
            all_base_candidates.add(base)
            slots.append({
                "index": index,
                "start_offset": index * slot_bytes,
                "sha256": digest,
                "candidate_ram_base": f"0x{base:08X}",
                "pointer_count": POINTER_COUNT,
                "type_0x41_entries_at_indices_2_to_40": tag_41_count,
                "type_0x41_span_rule_matches": rule_matches,
                "palette_sized_512_count": sum(palette_sized),
                "palette_size_exception_indices": [
                    j for j, matched in zip(PALETTE_INDICES, palette_sized)
                    if not matched
                ],
                "paired_0x8000_marker_count": data_marker_count,
                "final_pointer_relative_offset": offsets[-1],
                "last_entry_max_bytes_to_slot_end": slot_bytes - offsets[-1],
            })
    duplicate_groups = [indices for indices in duplicates.values()
                        if len(indices) > 1]
    duplicate_groups.sort(key=lambda group: group[0])
    return {
        "schema": 1,
        "kind": "WILD_ARMS_CDFLR_FIXED_SLOT_CATALOG",
        "source_name": path.name,
        "source_size_bytes": size,
        "slot_bytes": slot_bytes,
        "slot_count": count,
        "unique_sha256_count": len(duplicates),
        "duplicate_groups": duplicate_groups,
        "distinct_candidate_ram_bases": sorted(f"0x{b:08X}" for b in all_base_candidates),
        "slots_with_58_pointers": count,
        "slots_with_39_type_0x41_headers": sum(
            s["type_0x41_entries_at_indices_2_to_40"] == 39 for s in slots
        ),
        "slots_with_39_matching_span_rules": sum(
            s["type_0x41_span_rule_matches"] == 39 for s in slots
        ),
        "slots_with_all_8_palette_sized_spans": sum(
            s["palette_sized_512_count"] == 8 for s in slots
        ),
        "slots_with_all_8_data_markers": sum(
            s["paired_0x8000_marker_count"] == 8 for s in slots
        ),
        "palette_size_exception_slot_indices": [
            s["index"] for s in slots if s["palette_sized_512_count"] != 8
        ],
        "slots": slots,
        "interpretation": {
            "fixed_stride_is_observed_not_verified_gameplay_semantics": True,
            "pointer_base_is_inferred_not_runtime_proven": True,
            "palette_shapes_are_candidates_not_decoded_images": True,
            "last_entry_size_is_upper_bound_only": True,
            "original_payload_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource", type=Path, help="private original CDFLR.BIN")
    parser.add_argument("--slot-bytes", type=lambda s: int(s, 0),
                        default=DEFAULT_SLOT_BYTES)
    args = parser.parse_args()
    print(json.dumps(audit_fixed_slots(args.resource, args.slot_bytes),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
