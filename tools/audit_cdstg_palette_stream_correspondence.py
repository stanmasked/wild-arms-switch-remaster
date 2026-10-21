#!/usr/bin/env python3
"""Correlate 512-byte PS1 color-like banks and VERIFIED CDSTG LZSS regions.

This is structural association, NOT a verified bank -> stream CLUT mapping.
Uses the previously reviewed bounded LZSS validator; source stays private.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from audit_cdstg_map_lzss import audit_map_lzss

MAP_BYTES = 0x91000
GFX_START = 0x15000
GFX_BASE = 0x80164000
MAX_MAPS = 128


def audit_bank_stream_correspondence(path, *, map_bytes=MAP_BYTES,
                                    gfx_start=GFX_START, map_count=MAX_MAPS,
                                    dummy_index=25):
    if (type(map_count) is not int or not 1 <= map_count <= MAX_MAPS or
            type(dummy_index) is not int or not 0 <= dummy_index < map_count):
        raise ValueError("invalid map count or dummy index")
    if (type(map_bytes) is not int or type(gfx_start) is not int or
            map_bytes % 4 or not 0x600 <= map_bytes <= MAP_BYTES or
            gfx_start % 4 or not 0x100 <= gfx_start <= map_bytes - 0x104):
        raise ValueError("invalid fixed-map/graphics geometry")
    path = Path(path)
    if path.stat().st_size != map_bytes * map_count:
        raise ValueError("CDSTG is not an exact fixed-length map collection")

    # Reuse the already tested authentic WA1 decoder and strict next-pointer
    # endpoint checks; never count a matching 0x8000/0x10000 header alone.
    streams = audit_map_lzss(
        path, map_bytes=map_bytes, graphics_offset=gfx_start,
        map_count=map_count, dummy_index=dummy_index)
    stream_counts = {
        row["map_index"]: row["fully_bounded_lzss_streams"]
        for row in streams["per_map"] if row["status"] == "SCANNED"
    }
    indices = {}
    for row in streams["decoded_stream_fingerprints"]:
        indices.setdefault(row["map_index"], []).append(
            row["candidate_region_index"])
    counts = Counter()
    relationships = []
    with path.open("rb") as src:
        for map_index in range(map_count):
            block = src.read(map_bytes)
            if len(block) != map_bytes:
                raise ValueError("truncated original map during correlation")
            if map_index == dummy_index:
                relationships.append({"map_index": map_index,
                                      "status": "DUMMY_UNCLASSIFIED"})
                continue
            graphic = memoryview(block)[gfx_start:]
            if len(graphic) < 8:
                raise ValueError("map graphics area has no pointer header")
            first, second = struct.unpack_from("<II", graphic)
            start = first - GFX_BASE
            end = second - GFX_BASE
            if (start != 0x100 or first % 4 or second % 4 or
                    not 0x100 < end <= len(graphic)):
                raise ValueError(f"map {map_index}: invalid first graphics region")
            length = end - start
            banks = length // 512 if length % 512 == 0 else None
            decoded = stream_counts.get(map_index)
            if decoded is None:
                raise ValueError(f"map {map_index}: missing validated stream report")
            mismatch = None if banks is None else banks - decoded
            status = ("UNALIGNED_CANDIDATE_BANKS" if banks is None
                      else "COUNT_MATCH" if banks == decoded
                      else "EXTRA_CANDIDATE_BANKS" if banks > decoded
                      else "MORE_STREAMS_THAN_BANKS")
            counts[status] += 1
            section = graphic[start:end]
            relationships.append({
                "map_index": map_index,
                "candidate_palette_region_bytes": length,
                "candidate_512_byte_banks": banks,
                "verified_lzss_region_count": decoded,
                "candidate_lzss_region_indices": sorted(indices.get(map_index, [])),
                "count_difference": mismatch,
                "classification": status,
                "candidate_palette_region_sha256": hashlib.sha256(section).hexdigest(),
                "per_bank_palette_assignment_unverified": True,
            })
    return {
        "schema": 1,
        "kind": "WA1_CDSTG_CANDIDATE_BANK_TO_VERIFIED_STREAM_COUNTS",
        "source_name": path.name,
        "map_count": map_count,
        "dummy_map_index": dummy_index,
        "ordinary_maps": map_count - 1,
        "count_match_map_count": counts["COUNT_MATCH"],
        "extra_bank_map_count": counts["EXTRA_CANDIDATE_BANKS"],
        "more_streams_map_count": counts["MORE_STREAMS_THAN_BANKS"],
        "unaligned_bank_map_count": counts["UNALIGNED_CANDIDATE_BANKS"],
        "mismatching_map_indices": [
            row["map_index"] for row in relationships
            if row.get("classification") not in (None, "COUNT_MATCH")
        ],
        "maps": relationships,
        "interpretation": {
            "one_512_byte_bank_per_stream_is_a_hypothesis_only": True,
            "bank_ordinal_to_stream_ordinal_not_verified": True,
            "candidate_palette_rows_not_verified_vram_cluts": True,
            "this_is_not_a_map_renderer_or_runtime_gpu_trace": True,
            "no_original_pixels_or_color_values_emitted": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdstg", type=Path, help="private original CDSTG.BIN")
    args = parser.parse_args()
    print(json.dumps(audit_bank_stream_correspondence(args.cdstg),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
