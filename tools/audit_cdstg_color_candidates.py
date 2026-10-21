#!/usr/bin/env python3
"""Metadata-only audit of candidate PS1 color rows and offset tables in maps.

The format hypotheses in this tool are deliberately weaker than a verified
VRAM transfer/renderer. Do not claim that 16-bit color-like rows are actual
CLUTs or that offset sequences select a particular map's tiles.
No original image bytes, palettes or maps are emitted.
"""
import argparse
from collections import Counter
import hashlib
import json
import struct
from pathlib import Path

MAP_BYTES = 0x91000
GFX_OFFSET = 0x15000
GFX_BASE = 0x80164000
MAX_MAPS = 128
ROW_WORDS = 16
ROW_BYTES = ROW_WORDS * 2
BANK_BYTES = 512


def leading_offsets_within_region(data, *, max_offsets=512):
    """Return a strictly increasing leading *candidate* offset run.

    The first offset must be zero. These are region-relative word values
    rather than proven file pointers and may belong to another structure.
    """
    if len(data) < 16 or len(data) % 4:
        return []
    count = min(max_offsets, len(data) // 4)
    first, = struct.unpack_from("<I", data)
    if first != 0:
        return []
    positions = [0]
    for index in range(1, count):
        value, = struct.unpack_from("<I", data, 4*index)
        if value % 4 or value <= positions[-1] or value >= len(data):
            break
        positions.append(value)
    return positions if len(positions) >= 4 else []


def audit_cdstg_color_candidates(path, *, map_count=MAX_MAPS,
                                  map_bytes=MAP_BYTES,
                                  gfx_offset=GFX_OFFSET, dummy_index=25):
    if (type(map_count) is not int or not 1 <= map_count <= MAX_MAPS or
            type(dummy_index) is not int or not 0 <= dummy_index < map_count):
        raise ValueError("invalid map_count or dummy_index")
    if (type(map_bytes) is not int or type(gfx_offset) is not int or
            map_bytes % 4 or not 0x1000 <= map_bytes <= MAP_BYTES or
            gfx_offset % 4 or not 0x100 <= gfx_offset <= map_bytes-0x400):
        raise ValueError("invalid map graphics geometry")
    path = Path(path)
    file_size = path.stat().st_size
    if file_size != map_count * map_bytes:
        raise ValueError("CDSTG file size differs from declared fixed records")

    maps = []
    all_first_banks_multiple = 0
    all_fifth_regions_row_multiple = 0
    distinct_first_region_hashes = set()
    with path.open("rb") as source:
        for map_index in range(map_count):
            block = source.read(map_bytes)
            if len(block) != map_bytes:
                raise ValueError("short read during private map audit")
            if map_index == dummy_index:
                maps.append({"map_index": map_index,
                             "status": "DUMMY_UNCLASSIFIED"})
                continue
            graphics = block[gfx_offset:]
            if len(graphics) < 256:
                raise ValueError("graphics area is too small")
            words = struct.unpack_from("<64I", graphics)
            positions = []
            for pointer in words:
                local = pointer - GFX_BASE
                if (pointer % 4 or local < 256 or local > len(graphics)-4 or
                        (positions and local <= positions[-1])):
                    break
                positions.append(local)
            if len(positions) < 7 or len(positions) == 64 or positions[0] != 256:
                raise ValueError(f"map {map_index}: no safe graphics pointer run")

            # Region 0 is the only region exhaustively checked for 16-word
            # color-row geometry; no values/colors leave the private process.
            first = graphics[positions[0]:positions[1]]
            row_aligned = len(first) % ROW_BYTES == 0
            bank_aligned = len(first) % BANK_BYTES == 0
            all_first_banks_multiple += int(bank_aligned)
            row_hash_counts = Counter()
            zero_rows = 0
            rows_beginning_zero = 0
            any_high_bit_rows = 0
            if row_aligned:
                for pos in range(0, len(first), ROW_BYTES):
                    line = first[pos:pos+ROW_BYTES]
                    words16 = struct.unpack("<16H", line)
                    row_hash_counts[hashlib.sha256(line).hexdigest()] += 1
                    zero_rows += int(not any(words16))
                    rows_beginning_zero += int(words16[0] == 0)
                    any_high_bit_rows += int(any(c & 0x8000 for c in words16))
            digest = hashlib.sha256(first).hexdigest()
            distinct_first_region_hashes.add(digest)
            fifth_region = graphics[positions[5]:positions[6]]
            all_fifth_regions_row_multiple += int(
                len(fifth_region) % ROW_BYTES == 0)

            # Inspect the trailing regions only as bounded *offset-pattern*
            # candidates. The final item has no true next pointer, so use
            # its slot-end region only as a maximum extent.
            tails = []
            for section_index in (len(positions)-2, len(positions)-1):
                start = positions[section_index]
                end = (positions[section_index+1]
                       if section_index+1 < len(positions)
                       else len(graphics))
                extent = graphics[start:end]
                possible_offsets = leading_offsets_within_region(extent)
                tails.append({
                    "region_index": section_index,
                    "region_max_extent_bytes": len(extent),
                    "end_verified_by_next_pointer": section_index+1 < len(positions),
                    "leading_internal_offset_run_count": len(possible_offsets),
                    "internal_offset_run_last_max": (possible_offsets[-1]
                                                     if possible_offsets else None),
                })
            maps.append({
                "map_index": map_index,
                "status": "STRUCTURAL_CANDIDATES",
                "graphics_pointer_count": len(positions),
                "first_region_bytes": len(first),
                "first_region_sha256": digest,
                "first_region_multiple_of_512": bank_aligned,
                "first_region_color_like_16_word_rows":
                    len(first) // ROW_BYTES if row_aligned else None,
                "first_region_unique_16_word_rows": (
                    len(row_hash_counts) if row_aligned else None),
                "first_region_all_zero_16_word_rows": zero_rows,
                "first_region_16_word_rows_beginning_zero": rows_beginning_zero,
                "first_region_16_word_rows_with_bit15_set": any_high_bit_rows,
                "region_5_bytes": len(fifth_region),
                "region_5_multiple_of_32": len(fifth_region) % ROW_BYTES == 0,
                "final_region_offset_table_hypotheses": tails,
            })
    standard = map_count - 1
    return {
        "schema": 1,
        "kind": "WA1_CDSTG_CANDIDATE_COLOR_ROWS_AND_INTERNAL_OFFSETS",
        "source_name": path.name,
        "source_size_bytes": file_size,
        "map_count": map_count,
        "ordinary_maps": standard,
        "dummy_map_index": dummy_index,
        "first_region_multiple_of_512_count": all_first_banks_multiple,
        "region_5_multiple_of_32_count": all_fifth_regions_row_multiple,
        "first_region_distinct_sha256_count": len(distinct_first_region_hashes),
        "maps": maps,
        "interpretation": {
            "color_words_are_bgr555_hypothesis_only": True,
            "row_groups_are_not_verified_clut_rows": True,
            "region_five_role_not_proven": True,
            "internal_offset_run_not_tile_placement_proof": True,
            "last_map_region_extent_upper_bound_only": True,
            "decoded_pixels_emitted": False,
            "original_source_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdstg", type=Path, help="PRIVATE user-owned CDSTG.BIN")
    args = parser.parse_args()
    print(json.dumps(audit_cdstg_color_candidates(args.cdstg),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
