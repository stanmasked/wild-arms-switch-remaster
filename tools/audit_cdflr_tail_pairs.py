#!/usr/bin/env python3
"""Audit candidate palette/data pair signatures at the tail of CDFLR.BIN.

Metadata-only and read-only. The apparent palettes are not proven palettes;
the paired data blocks are not decoded or labelled as graphical assets.
No source bytes are emitted.
"""
import argparse
import json
import struct
from pathlib import Path

PREFIX_BYTES = 256
FIRST_PALETTE_INDEX = 42
LAST_PALETTE_INDEX = 56
TABLE_ENTRIES = 58
EXPECTED_PALETTE_BYTES = 512
CANDIDATE_DATA_FIRST_WORD = 0x00008000
LOW_RAM = 0x80000000
HIGH_RAM = 0x80200000


def audit_tail(path):
    path = Path(path)
    file_size = path.stat().st_size
    if file_size < PREFIX_BYTES + 4:
        raise ValueError("file is too short for the candidate pointer table")
    with path.open("rb") as source:
        prefix = source.read(PREFIX_BYTES)
        words = struct.unpack("<64I", prefix)
        if not all(LOW_RAM <= w < HIGH_RAM and w % 4 == 0
                   for w in words[:TABLE_ENTRIES]):
            raise ValueError("invalid RAM-like pointer in the 58-entry table")
        if words[TABLE_ENTRIES] != 0 or any(prefix[(TABLE_ENTRIES + 1) * 4:]):
            raise ValueError("pointer table terminator or padding invalid")
        addresses = words[:TABLE_ENTRIES]
        if any(n <= p for p, n in zip(addresses, addresses[1:])):
            raise ValueError("pointer table is not strictly increasing")
        base_candidate = addresses[0] - PREFIX_BYTES
        offsets = [a - base_candidate for a in addresses]
        if offsets[0] != PREFIX_BYTES or any(o + 4 > file_size for o in offsets):
            raise ValueError("candidate offsets exceed source-file bounds")

        palette_rows = []
        data_rows = []
        for palette_index in range(FIRST_PALETTE_INDEX, LAST_PALETTE_INDEX + 1, 2):
            palette_start = offsets[palette_index]
            data_index = palette_index + 1
            palette_end = offsets[data_index]
            palette_size = palette_end - palette_start
            palette_exact_512 = palette_size == EXPECTED_PALETTE_BYTES
            unique_u16 = None
            if palette_exact_512:
                source.seek(palette_start)
                palette = source.read(EXPECTED_PALETTE_BYTES)
                if len(palette) != EXPECTED_PALETTE_BYTES:
                    raise ValueError("palette-sized candidate truncated")
                unique_u16 = len(set(struct.unpack("<256H", palette)))

            data_start = offsets[data_index]
            source.seek(data_start)
            raw_prefix = source.read(4)
            if len(raw_prefix) != 4:
                raise ValueError("data candidate prefix truncated")
            first_word = struct.unpack("<I", raw_prefix)[0]
            has_next = data_index < TABLE_ENTRIES - 1
            known_span = offsets[data_index + 1] - data_start if has_next else None
            palette_rows.append({
                "index": palette_index,
                "span_bytes": palette_size,
                "exactly_512_bytes": palette_exact_512,
                "distinct_u16_values_if_512": unique_u16,
            })
            data_rows.append({
                "index": data_index,
                "first_word_0x8000": first_word == CANDIDATE_DATA_FIRST_WORD,
                "next_pointer_span_bytes": known_span,
                "last_span_is_unknown": not has_next,
            })

    known_spans = [r["next_pointer_span_bytes"] for r in data_rows
                   if r["next_pointer_span_bytes"] is not None]
    distinct_u16 = [r["distinct_u16_values_if_512"] for r in palette_rows
                    if r["distinct_u16_values_if_512"] is not None]
    return {
        "schema": 1,
        "kind": "PRIVATE_CDFLR_TAIL_PAIR_AUDIT",
        "source_name": path.name,
        "source_size_bytes": file_size,
        "pointer_table_entries": TABLE_ENTRIES,
        "base_address_is_inferred": True,
        "candidate_palette_indices": [r["index"] for r in palette_rows],
        "palette_candidate_count": len(palette_rows),
        "palette_exact_512_count": sum(r["exactly_512_bytes"] for r in palette_rows),
        "palette_distinct_u16_min": min(distinct_u16) if distinct_u16 else None,
        "palette_distinct_u16_max": max(distinct_u16) if distinct_u16 else None,
        "candidate_data_indices": [r["index"] for r in data_rows],
        "data_candidate_count": len(data_rows),
        "data_first_word_0x8000_count": sum(r["first_word_0x8000"] for r in data_rows),
        "bounded_next_pointer_data_span_count": len(known_spans),
        "bounded_next_pointer_data_span_min": min(known_spans) if known_spans else None,
        "bounded_next_pointer_data_span_max": max(known_spans) if known_spans else None,
        "last_data_span_length_unknown": data_rows[-1]["last_span_is_unknown"],
        "palette_candidates": palette_rows,
        "data_candidates": data_rows,
        "interpretation": {
            "status": "STRUCTURAL_PAIR_CANDIDATES_ONLY",
            "palette_and_image_meanings_unverified": True,
            "last_data_end_not_established": True,
            "original_payload_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="private local CDFLR.BIN")
    args = parser.parse_args()
    print(json.dumps(audit_tail(args.path), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
