#!/usr/bin/env python3
"""Private-original geometry hypotheses for decoded Wild Arms CDSTG graphics.

Quantitative texture candidates only: no pixel export, no palette assumptions,
no map rendering, and no claim that adjacency statistics prove dimensions.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import struct
from pathlib import Path
from wa1_lzss import LZSSDecodeError, decode_wa1_lzss

MAP_BYTES = 0x91000
GRAPHICS_START = 0x15000
GRAPHICS_BASE = 0x80164000
KNOWN_OUTPUT_BYTES = (0x8000, 0x10000)


def pixel_layout_hypotheses(decoded):
    """Analyze hypothetical unpacked 4bpp and raw 8bpp row-major views."""
    four_bit = bytearray(2 * len(decoded))
    for i, byte in enumerate(decoded):
        four_bit[2*i] = byte & 15
        four_bit[2*i+1] = byte >> 4
    guesses = []
    for bpp, pixels in ((4, four_bit), (8, decoded)):
        length = len(pixels)
        frequencies = Counter(pixels)
        random_pair_baseline = sum((n / length) ** 2 for n in frequencies.values())
        for width in (128, 256, 512, 1024):
            if length % width:
                continue
            height = length // width
            if not 64 <= height <= 1024:
                continue
            horizontal_pairs = length - height
            vertical_pairs = length - width
            horizontal_same = sum(
                pixels[k] == pixels[k+1] for k in range(length-1)
                if (k+1) % width)
            vertical_same = sum(
                pixels[k] == pixels[k+width] for k in range(vertical_pairs))
            guesses.append({
                "assumed_bits_per_pixel": bpp,
                "assumed_width": width,
                "assumed_height": height,
                "used_index_values": len(frequencies),
                "horizontal_neighbor_equal_ratio": round(
                    horizontal_same / horizontal_pairs, 6),
                "vertical_neighbor_equal_ratio": round(
                    vertical_same / vertical_pairs, 6),
                "frequency_only_equal_pair_baseline": round(
                    random_pair_baseline, 6),
            })
    return guesses


def audit_surf_layout(path, *, map_index=2, map_bytes=MAP_BYTES,
                      graphics_offset=GRAPHICS_START, map_count=128,
                      dummy_map_index=25):
    if (type(map_index) is not int or type(map_count) is not int or
            not 1 <= map_count <= 128 or not 0 <= map_index < map_count or
            map_index == dummy_map_index):
        raise ValueError("invalid map selection (or exceptional dummy)")
    if (type(map_bytes) is not int or type(graphics_offset) is not int or
            not 0x600 <= map_bytes <= MAP_BYTES or map_bytes % 4 or
            not 0x100 <= graphics_offset < map_bytes - 0x104 or
            graphics_offset % 4):
        raise ValueError("invalid map/graphics geometry")
    path = Path(path)
    if path.stat().st_size != map_bytes * map_count:
        raise ValueError("CDSTG size disagrees with fixed-map geometry")
    with path.open("rb") as src:
        src.seek(map_index * map_bytes)
        graphics = src.read(map_bytes)[graphics_offset:]
    if len(graphics) != map_bytes - graphics_offset:
        raise ValueError("short map read")
    pointers = struct.unpack_from("<64I", graphics)
    offsets = []
    for addr in pointers:
        pos = addr - GRAPHICS_BASE
        if (addr % 4 or pos < 256 or pos > len(graphics)-4 or
                (offsets and pos <= offsets[-1])):
            break
        offsets.append(pos)
    if len(offsets) < 2 or len(offsets) == 64 or offsets[0] != 256:
        raise ValueError("invalid leading graphics pointer table")

    found, rejected = [], []
    for j in range(len(offsets)-1):
        start, end = offsets[j:j+2]
        encoded = graphics[start:end]
        if len(encoded) < 4:
            continue
        expected = struct.unpack_from("<I", encoded)[0]
        if expected not in KNOWN_OUTPUT_BYTES:
            continue
        try:
            decoded, consumed = decode_wa1_lzss(encoded, max_output=0x10000)
            if len(decoded) != expected or len(encoded) - consumed not in range(4):
                raise LZSSDecodeError("compressed stream boundary mismatch")
        except LZSSDecodeError as exc:
            rejected.append({"region_index": j, "reason": str(exc)})
            continue
        histogram = Counter(decoded)
        n = len(decoded)
        entropy = -sum((v/n)*math.log2(v/n) for v in histogram.values())
        zeros = sum((byte & 15 == 0) + (byte >> 4 == 0) for byte in decoded)
        found.append({
            "region_index": j,
            "bounded_encoded_bytes": len(encoded),
            "consumed_encoded_bytes": consumed,
            "unused_alignment_bytes": len(encoded)-consumed,
            "decoded_bytes": n,
            "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
            "distinct_byte_values": len(histogram),
            "entropy_bits_per_byte": round(entropy, 6),
            "fraction_of_zero_nibbles": round(zeros/(2*n), 6),
            "candidate_layouts": pixel_layout_hypotheses(decoded),
        })
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_MAP_TEXTURE_LAYOUT_HYPOTHESES",
        "source_name": path.name,
        "map_index": map_index,
        "graphics_pointer_count": len(offsets),
        "next_pointer_bounded_regions": len(offsets)-1,
        "verified_lzss_regions": len(found),
        "verified_streams": found,
        "rejected_header_like_regions": rejected,
        "interpretation": {
            "four_bpp_low_nibble_first_is_only_a_hypothesis_for_maps": True,
            "eight_bpp_is_a_competing_hypothesis": True,
            "candidate_dimensions_not_proven": True,
            "palette_and_tile_layout_not_proven": True,
            "final_unbounded_region_not_examined": True,
            "game_source_pixels_emitted": False,
            "no_rendered_game_scene_produced": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdstg", type=Path, help="private original CDSTG.BIN")
    parser.add_argument("--map-index", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(audit_surf_layout(args.cdstg, map_index=args.map_index),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
