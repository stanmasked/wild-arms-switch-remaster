#!/usr/bin/env python3
"""Metadata-only inventory of original Wild Arms (USA) CDSTG map records.

Map geometry, script pointers and the variable-sized graphics pointer list
are checked without decoding/copying original bytes. Independent reference:
Christian Bauer, wa1tools, mapinfo / wa/map.py (ISC license).
https://github.com/cebix/wa1tools

No original executable, maps, dialogue, compressed textures, screenshots,
map names or other source assets belong in public GitHub or CI.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

MAP_BYTES = 0x91000
GRAPHICS_OFFSET = 0x15000
MAP_RAM_BASE = 0x8014F000
GRAPHICS_RAM_BASE = 0x80164000
GRAPHICS_TABLE_BYTES = 0x100
MAP_POINTER_TABLE_OFFSET = 0x40
MAP_POINTER_COUNT = 18
MAX_MAPS = 128
MAP_NAME_POINTERS_EXE_OFFSET = 0x7578
EXE_RAM_TEXT_BASE = 0x80011420
EXE_HEADER_BYTES = 0x800


def _read_names_from_original_exe(path, map_count):
    data = Path(path).read_bytes()
    if len(data) < EXE_HEADER_BYTES or data[:8] != b"PS-X EXE":
        raise ValueError("expected original PS-X EXE header")
    if MAP_NAME_POINTERS_EXE_OFFSET + map_count * 4 > len(data):
        raise ValueError("EXE map-name pointer table beyond file")
    names = []
    for i in range(map_count):
        ptr = struct.unpack_from("<I", data, MAP_NAME_POINTERS_EXE_OFFSET + i * 4)[0]
        start = ptr - EXE_RAM_TEXT_BASE + EXE_HEADER_BYTES
        if start < EXE_HEADER_BYTES or start >= len(data):
            raise ValueError(f"map {i}: name pointer outside EXE")
        end = data.find(b"\x00", start, min(start + 96, len(data)))
        if end < 0:
            raise ValueError(f"map {i}: name string not terminated within 96 bytes")
        # Literal text is only part of an OPTIONAL private report; actual
        # game localization/encoding requires the upstream WA1 text decoder.
        names.append(data[start:end].decode("latin-1"))
    return names


def audit_cdstg_maps(resource, *, map_bytes=MAP_BYTES,
                     graphics_offset=GRAPHICS_OFFSET, map_count=MAX_MAPS,
                     dummy_index=25, executable=None, include_names=False):
    if (type(map_bytes) is not int or type(graphics_offset) is not int or
            not 512 <= map_bytes <= MAP_BYTES or map_bytes % 4 or
            not 0x100 <= graphics_offset <= map_bytes - 0x104 or
            graphics_offset % 4):
        raise ValueError("invalid bounded map/graphics geometry")
    if type(map_count) is not int or not 1 <= map_count <= MAX_MAPS:
        raise ValueError("map_count must be 1..128")
    if type(dummy_index) is not int or dummy_index < 0 or dummy_index >= map_count:
        raise ValueError("dummy_index must select a map within the file")
    if include_names and executable is None:
        raise ValueError("include_names requires a PRIVATE original EXE")
    source = Path(resource)
    if source.stat().st_size != map_count * map_bytes:
        raise ValueError("CDSTG is not the declared exact fixed-map geometry")
    names = (_read_names_from_original_exe(executable, map_count)
             if include_names else None)
    inventory = []
    counts = {}
    gfx_sha = set()
    script_ptr_issues = []
    exceptional = []
    with source.open("rb") as stream:
        for index in range(map_count):
            block = stream.read(map_bytes)
            if len(block) != map_bytes:
                raise ValueError("map file became truncated while reading")
            image = block[graphics_offset:]
            entry = {"map_index": index,
                     "byte_offset": index * map_bytes,
                     "graphics_byte_offset_in_map": graphics_offset,
                     "graphics_extent_max_bytes": len(image),
                     "graphics_region_sha256": hashlib.sha256(image).hexdigest()}
            if names is not None:
                entry["map_name_raw_private"] = names[index]
            gfx_sha.add(entry["graphics_region_sha256"])
            if index == dummy_index:
                exceptional.append(index)
                entry["status"] = "DUMMY_UNCLASSIFIED"
                inventory.append(entry)
                continue

            # Exact layout of this pointer table is documented in WA1Tools.
            if struct.unpack_from("<I", block, 8)[0] != MAP_RAM_BASE + 0x40:
                raise ValueError(f"map {index}: unknown executable-like header")
            script_ptrs = struct.unpack_from("<18I", block, MAP_POINTER_TABLE_OFFSET)
            for j, pointer in enumerate(script_ptrs):
                if pointer and not (MAP_RAM_BASE <= pointer < MAP_RAM_BASE + graphics_offset):
                    raise ValueError(f"map {index}: script table pointer {j} out of bounds")
                if pointer and pointer % 2:
                    raise ValueError(f"map {index}: script pointer {j} unaligned")
            # Index #6 = global entries and #7 = script-1, with halfword
            # script-entry addresses. Zero optional pointers are allowed.
            if (not script_ptrs[6] or not script_ptrs[7] or
                    script_ptrs[7] < script_ptrs[6] or
                    (script_ptrs[7] - script_ptrs[6]) % 2):
                script_ptr_issues.append(index)
                raise ValueError(f"map {index}: script-entry table invalid")
            entry["script_table_nonzero_pointer_count"] = sum(bool(p) for p in script_ptrs)
            entry["script_entry_table_offset"] = script_ptrs[6] - MAP_RAM_BASE
            entry["script_1_offset"] = script_ptrs[7] - MAP_RAM_BASE
            entry["global_script_entry_count"] = (script_ptrs[7] - script_ptrs[6]) // 2
            entry["has_script_2"] = bool(script_ptrs[8])

            # A separate independent graphics region starts at map offset
            # 0x15000, loaded at 0x80164000 (WA1Tools mapGfxPointer).
            # Only a strictly increasing leading run is considered candidate
            # pointers. Remaining bytes are opaque, NOT a zero sentinel.
            if len(image) < GRAPHICS_TABLE_BYTES:
                raise ValueError("graphics area is too short")
            raw_words = struct.unpack_from("<64I", image)
            candidates = []
            for word in raw_words:
                local = word - GRAPHICS_RAM_BASE
                if (word % 4 or not GRAPHICS_TABLE_BYTES <= local <=
                        len(image) - 4 or
                        (candidates and local <= candidates[-1])):
                    break
                candidates.append(local)
            if len(candidates) < 2 or len(candidates) >= 64 or candidates[0] != 0x100:
                raise ValueError(f"map {index}: invalid candidate graphics pointer run")
            entry["candidate_graphics_pointer_count"] = len(candidates)
            entry["first_graphics_pointer_offset"] = candidates[0]
            entry["last_graphics_pointer_offset"] = candidates[-1]
            entry["first_graphics_item_max_bytes"] = candidates[1] - candidates[0]
            entry["last_graphics_item_max_bytes"] = len(image) - candidates[-1]
            entry["last_graphics_item_end_unverified"] = True
            entry["script_and_graphics_not_yet_playable_scene"] = True
            counts[len(candidates)] = counts.get(len(candidates), 0) + 1
            entry["status"] = "STRUCTURALLY_INDEXED"
            inventory.append(entry)
    return {
        "schema": 1,
        "kind": "WA1_CDSTG_MAP_AND_GRAPHICS_POINTER_CATALOG",
        "source_name": source.name,
        "source_size_bytes": source.stat().st_size,
        "map_bytes": map_bytes,
        "map_count": map_count,
        "graphics_area_offset": graphics_offset,
        "graphics_area_size": map_bytes - graphics_offset,
        "dummy_map_indices": exceptional,
        "structurally_indexed_maps": len(inventory) - len(exceptional),
        "unique_full_graphics_region_sha256_count": len(gfx_sha),
        "candidate_graphics_pointer_count_histogram": {
            str(k): counts[k] for k in sorted(counts)},
        "maps": inventory,
        "interpretation": {
            "script_sections_have_not_been_executed": True,
            "graphics_pointer_run_is_structural_hypothesis": True,
            "graphics_region_is_not_a_decoded_image": True,
            "last_graphics_item_end_is_upper_bound_only": True,
            "original_source_bytes_emitted": False,
            "names_from_exe_only_when_explicitly_requested_privately": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdstg", type=Path, help="private user-owned CDSTG.BIN")
    parser.add_argument("--executable", type=Path,
                        help="private WILDARMS.EXE, only for --include-names")
    parser.add_argument("--include-names", action="store_true",
                        help="include original text only in a PRIVATE local report")
    args = parser.parse_args()
    print(json.dumps(audit_cdstg_maps(
        args.cdstg, executable=args.executable, include_names=args.include_names),
        sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
