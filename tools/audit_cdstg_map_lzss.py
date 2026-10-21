#!/usr/bin/env python3
"""Check candidate compressed graphics sections in user-owned WA1 CDSTG maps.

Reuses the exact, bounded Wild Arms 1 LZSS decoder from Stage420. Only
independent map-graphics sections *with a following pointer* are tested.
A coincidental 0x8000/0x10000 prefix is never treated as proof of a codec.
Only metadata and SHA-256 fingerprints are emitted; no original pixels.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from wa1_lzss import LZSSDecodeError, decode_wa1_lzss

DEFAULT_MAP_BYTES = 0x91000
DEFAULT_GFX_OFFSET = 0x15000
GFX_BASE = 0x80164000
MAX_MAPS = 128
SUPPORTED_OUTPUT_BYTES = (0x8000, 0x10000)


def audit_map_lzss(path, *, map_bytes=DEFAULT_MAP_BYTES,
                   graphics_offset=DEFAULT_GFX_OFFSET,
                   map_count=MAX_MAPS, dummy_index=25):
    if (type(map_bytes) is not int or type(graphics_offset) is not int or
            not 0x600 <= map_bytes <= DEFAULT_MAP_BYTES or map_bytes % 4 or
            not 0x100 <= graphics_offset <= map_bytes - 0x104 or
            graphics_offset % 4):
        raise ValueError("invalid map and graphics geometry")
    if type(map_count) is not int or not 1 <= map_count <= MAX_MAPS:
        raise ValueError("invalid map_count")
    if type(dummy_index) is not int or not 0 <= dummy_index < map_count:
        raise ValueError("invalid dummy_index")
    path = Path(path)
    if path.stat().st_size != map_bytes * map_count:
        raise ValueError("not an exact fixed-record CDSTG source")
    valid = 0
    marker_matches = 0
    output_counts = {hex(n): 0 for n in SUPPORTED_OUTPUT_BYTES}
    failures = []
    instances = []
    per_map = []
    with path.open("rb") as stream:
        for map_index in range(map_count):
            map_block = stream.read(map_bytes)
            if len(map_block) != map_bytes:
                raise ValueError("short read while auditing CDSTG")
            if map_index == dummy_index:
                per_map.append({"map_index": map_index,
                                "status": "DUMMY_NOT_SCANNED"})
                continue
            graphics = map_block[graphics_offset:]
            ptr = struct.unpack_from("<64I", graphics)
            offsets = []
            for addr in ptr:
                pos = addr - GFX_BASE
                if (addr % 4 or not 0x100 <= pos <= len(graphics) - 4
                        or (offsets and pos <= offsets[-1])):
                    break
                offsets.append(pos)
            if len(offsets) < 2 or len(offsets) == 64 or offsets[0] != 0x100:
                raise ValueError(f"map {map_index}: invalid graphics pointer run")
            good_here = 0
            for region in range(len(offsets) - 1):
                begin, end = offsets[region:region + 2]
                encoded = graphics[begin:end]
                prefix = struct.unpack_from("<I", encoded)[0]
                if prefix not in SUPPORTED_OUTPUT_BYTES:
                    continue
                marker_matches += 1
                site = {"map_index": map_index,
                        "candidate_region_index": region,
                        "declared_output_bytes": prefix,
                        "available_encoded_bytes": len(encoded)}
                try:
                    decoded, used = decode_wa1_lzss(
                        encoded, max_output=max(SUPPORTED_OUTPUT_BYTES))
                except LZSSDecodeError as exc:
                    failures.append(dict(site, classification="DECODE_REJECTED",
                                         reason=str(exc)))
                    continue
                spare = len(encoded) - used
                if spare not in (0, 1, 2, 3):
                    failures.append(dict(site,
                                         classification="BOUNDARY_MISMATCH",
                                         spare_encoded_bytes=spare))
                    continue
                if len(decoded) != prefix:
                    raise AssertionError("decoder returned wrong declared size")
                valid += 1
                good_here += 1
                output_counts[hex(prefix)] += 1
                instances.append({
                    **site,
                    "consumed_encoded_bytes": used,
                    "alignment_bytes": spare,
                    "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
                })
            per_map.append({
                "map_index": map_index,
                "status": "SCANNED",
                "candidate_graphics_pointer_count": len(offsets),
                "fully_bounded_lzss_streams": good_here,
            })
    return {
        "schema": 1,
        "kind": "WA1_CDSTG_MAP_BOUNDED_LZSS_AUDIT",
        "source_name": path.name,
        "map_count": map_count,
        "skipped_dummy_map_index": dummy_index,
        "candidate_0x8000_0x10000_prefix_count": marker_matches,
        "exactly_decoded_pointer_bounded_stream_count": valid,
        "decoded_output_byte_count_histogram": output_counts,
        "not_verified_candidates": failures,
        "decoded_stream_fingerprints": instances,
        "per_map": per_map,
        "interpretation": {
            "coincidental_header_words_may_trigger_rejected_candidates": True,
            "one_region_cannot_be_assumed_one_rendered_texture": True,
            "last_region_without_next_pointer_not_scanned": True,
            "no_original_decompressed_bytes_emitted": True,
            "real_ps1_scene_not_rendered": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdstg", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_map_lzss(args.cdstg), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
