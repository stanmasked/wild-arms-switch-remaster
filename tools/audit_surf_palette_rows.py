#!/usr/bin/env python3
"""Report PRIVATE Surf Village candidate BGR555 rows and WA1 index streams.

This module never outputs original pixel bytes or colors as public metadata.
Every 4bpp, palette-bank ordinal, width and STP choice is an UNVERIFIED
render hypothesis until checked against an original PS1 reference frame.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from wa1_lzss import LZSSDecodeError, decode_wa1_lzss

MAP_BYTES = 0x91000
GRAPHICS_OFFSET = 0x15000
GFX_RAM = 0x80164000
OUTPUT_LIMIT = 0x10000


def read_private_candidates(path, *, map_index=2, map_count=128,
                            map_bytes=MAP_BYTES,
                            graphics_offset=GRAPHICS_OFFSET,
                            dummy_index=25):
    """Return private in-memory candidate color banks + decompressed streams.

    Internal API: caller must not commit/export the returned source bytes.
    Only next-pointer-bounded original LZSS items can qualify.
    """
    if (type(map_index) is not int or type(map_count) is not int or
            type(dummy_index) is not int or not 1 <= map_count <= 128 or
            not 0 <= map_index < map_count or
            not 0 <= dummy_index < map_count or map_index == dummy_index):
        raise ValueError("invalid map index or dummy selection")
    if (type(map_bytes) is not int or type(graphics_offset) is not int or
            map_bytes % 4 or not 0x600 <= map_bytes <= MAP_BYTES or
            graphics_offset % 4 or not 0x100 <= graphics_offset <= map_bytes - 0x104):
        raise ValueError("invalid map/graphics geometry")
    path = Path(path)
    if path.stat().st_size != map_count * map_bytes:
        raise ValueError("CDSTG length does not match expected fixed map geometry")
    with path.open("rb") as source:
        source.seek(map_index * map_bytes)
        block = source.read(map_bytes)
    if len(block) != map_bytes:
        raise ValueError("map record truncated")
    graphics = block[graphics_offset:]
    if len(graphics) < 256:
        raise ValueError("graphics pointer header truncated")
    words = struct.unpack_from("<64I", graphics)
    offsets = []
    for word in words:
        relative = word - GFX_RAM
        if (word % 4 or not 0x100 <= relative <= len(graphics) - 4 or
                (offsets and relative <= offsets[-1])):
            break
        offsets.append(relative)
    if not 2 <= len(offsets) < 64 or offsets[0] != 0x100:
        raise ValueError("invalid increasing graphics pointer run")
    start, end = offsets[:2]
    palette_bytes = graphics[start:end]
    if len(palette_bytes) % 512:
        raise ValueError("candidate palette first region is not 512-byte aligned")
    bank_count = len(palette_bytes) // 512
    if not 1 <= bank_count <= 32:
        raise ValueError("candidate palette bank count outside 1..32")
    banks = [palette_bytes[i*512:(i+1)*512] for i in range(bank_count)]
    streams = []
    for i in range(len(offsets)-1):
        part = graphics[offsets[i]:offsets[i+1]]
        if len(part) < 4:
            continue
        proposed, = struct.unpack_from("<I", part)
        if proposed not in (0x8000, 0x10000):
            continue
        try:
            decoded, consumed = decode_wa1_lzss(part, max_output=OUTPUT_LIMIT)
        except LZSSDecodeError:
            continue
        if len(decoded) != proposed or len(part) - consumed not in (0,1,2,3):
            continue
        streams.append({"graphics_region_index": i, "decoded": decoded,
                        "consumed": consumed,
                        "alignment": len(part)-consumed,
                        "bounded_encoded_bytes": len(part)})
    return {"map_index": map_index, "candidate_banks": banks,
            "verified_streams": streams, "graphics_pointer_count": len(offsets),
            "last_graphics_region_not_bounded": True}


def unpack_candidate_4bpp(packed):
    """Low-nibble-first indexed pixels; hypothesis for CDSTG graphics."""
    if not isinstance(packed, (bytes,bytearray,memoryview)):
        raise TypeError("packed candidate pixels must be bytes-like")
    result = bytearray(len(packed)*2)
    for i, value in enumerate(packed):
        result[2*i] = value & 0x0F
        result[2*i+1] = value >> 4
    return bytes(result)


def bgr555_candidate_rgb(word):
    """Raw 15-bit BGR555 to RGB; bit15 ignored, no transparency semantics."""
    if type(word) is not int or not 0 <= word < 65536:
        raise ValueError("candidate color must be a u16")
    return ((word & 31)*255//31, ((word >> 5) & 31)*255//31,
            ((word >> 10) & 31)*255//31)


def audit_palette_candidates(path, **kwargs):
    private = read_private_candidates(path, **kwargs)
    banks = private["candidate_banks"]
    verified = private["verified_streams"]
    hashes = set()
    bank_reports = []
    for idx, bank in enumerate(banks):
        row_reports = []
        for row in range(16):
            row_bytes = bank[row*32:(row+1)*32]
            values = struct.unpack("<16H", row_bytes)
            digest = hashlib.sha256(row_bytes).hexdigest()
            hashes.add(digest)
            row_reports.append({
                "candidate_row_index": row,
                "candidate_row_sha256": digest,
                "unique_u16_count": len(set(values)),
                "zero_u16_count": sum(x == 0 for x in values),
                "first_color_word_zero": values[0] == 0,
                "high_bit_set_u16_count": sum(bool(x & 0x8000) for x in values),
            })
        bank_reports.append({"candidate_bank_index": idx,
                             "bank_sha256": hashlib.sha256(bank).hexdigest(),
                             "candidate_16_color_rows": row_reports})
    stream_reports = []
    for ord_idx, stream in enumerate(verified):
        data = stream["decoded"]
        counter = Counter(unpack_candidate_4bpp(data))
        stream_reports.append({
            "candidate_stream_ordinal": ord_idx,
            "graphics_region_index": stream["graphics_region_index"],
            "decoded_bytes": len(data),
            "decoded_sha256": hashlib.sha256(data).hexdigest(),
            "exact_encoded_bytes_used": stream["consumed"],
            "alignment_byte_count": stream["alignment"],
            "distinct_hypothetical_4bpp_indices": len(counter),
            "hypothetical_zero_index_pixel_count": counter[0],
            "hypothetical_4bpp_pixel_count": 2*len(data),
        })
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_SURF_COLOR_ROW_DIAGNOSTICS_METADATA",
        "source_name": Path(path).name,
        "map_index": private["map_index"],
        "graphics_pointer_count": private["graphics_pointer_count"],
        "candidate_512_byte_bank_count": len(banks),
        "verified_bounded_lzss_stream_count": len(verified),
        "same_bank_and_stream_count": len(banks)==len(verified),
        "candidate_16_color_row_count": 16*len(banks),
        "byte_distinct_palette_row_count": len(hashes),
        "all_zero_candidate_row_count": sum(
            row["zero_u16_count"] == 16
            for bank in bank_reports for row in bank["candidate_16_color_rows"]),
        "candidate_banks": bank_reports,
        "verified_streams": stream_reports,
        "interpretation": {
            "matching_bank_and_stream_ordinal_is_unverified": True,
            "choice_among_sixteen_rows_is_unverified": True,
            "ps1_stp_bit_and_alpha_are_unverified": True,
            "four_bit_row_major_layout_is_unverified": True,
            "no_verified_original_ps1_frame_match": True,
            "last_map_region_end_is_unverified": True,
            "no_original_palette_words_or_pixel_bytes_emitted": True,
        }
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_cdstg",type=Path)
    ap.add_argument("--map-index",type=int,default=2)
    args=ap.parse_args()
    print(json.dumps(audit_palette_candidates(
        args.private_cdstg,map_index=args.map_index),
        indent=2,sort_keys=True))


if __name__=="__main__":
    main()
