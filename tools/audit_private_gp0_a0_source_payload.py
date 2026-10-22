#!/usr/bin/env python3
"""PRIVATE direct comparison of complete GP0(A0) image words to decoded CDSTG.

Unlike matching a post-frame VRAM dump, this checks the supplied ordered
CPU-to-VRAM transfer payload itself, in its declared source order.
A match proves only equality inside an unverified packet trace. The
exporter does not acquire/authenticate original Wild Arms GP0 commands.
"""
import hashlib
import struct

from audit_private_surf_gp0_stream_uv_link import prepare_private_stream_index
from audit_private_surf_stream_vram_runs import (
    BLOCK_BYTES, VRAM_GRID_BYTES, VRAM_ROW_BYTES, MAX_RUN_SAMPLES,
)

MAX_TRANSFER_PIXELS = 1024 * 512
MAX_WORDS = 3 + (MAX_TRANSFER_PIXELS + 1) // 2


def match_a0_source_payload(index, packet, *, minimum_contiguous_blocks=3,
                            max_run_samples=8):
    """Report 64-byte contiguous source matches within a SINGLE A0 row.

    Source offset must be a 64-byte block boundary; A0 row offset may
    begin at any 32-byte boundary that yields a 16-halfword-aligned
    VRAM destination X. Partial source runs, odd last pixel padding
    and matches extending across transfer row boundaries are rejected.
    """
    if (type(index) is not dict or
            type(index.get("source_streams")) is not list or
            type(index.get("eligible_anchor_index")) is not dict or
            type(packet) is not list or not 4 <= len(packet) <= MAX_WORDS or
            any(type(word) is not int or not 0 <= word <= 0xffffffff
                for word in packet) or packet[0] >> 24 != 0xa0 or
            type(minimum_contiguous_blocks) is not int or
            not 2 <= minimum_contiguous_blocks <= 32 or
            type(max_run_samples) is not int or
            not 1 <= max_run_samples <= MAX_RUN_SAMPLES):
        raise ValueError("invalid GP0 A0 packet, indexed sources or search limits")
    x, y = packet[1] & 0xffff, packet[1] >> 16
    width, height = packet[2] & 0xffff, packet[2] >> 16
    if (not 1 <= width <= 1024 or not 1 <= height <= 512 or
            x + width > 1024 or y + height > 512 or
            len(packet) != 3 + (width*height + 1)//2):
        raise ValueError("GP0 A0 transfer geometry, padding or length invalid")
    # One 32-bit word always contains two LE 16-bit transferred pixels.
    payload = struct.pack("<%dI"%(len(packet)-3), *packet[3:])
    payload = payload[:width*height*2]  # Drop unused odd-pixel padding.
    row_size = width*2
    matches=[]
    total=0
    rows_scanned=0
    aligned_positions_scanned=0
    anchors_seen=0
    sources=index["source_streams"]
    anchors=index["eligible_anchor_index"]
    for row_index in range(height):
        row=payload[row_index*row_size:(row_index+1)*row_size]
        if row_size < BLOCK_BYTES * minimum_contiguous_blocks:
            continue
        rows_scanned += 1
        # A0 destination X is in u16 words, not bytes; enforce the
        # final *global VRAM* alignment rather than row-relative one.
        for offset in range(0, row_size-BLOCK_BYTES+1, VRAM_GRID_BYTES):
            global_x=x+offset//2
            if global_x % 16:
                continue
            aligned_positions_scanned += 1
            key=row[offset:offset+BLOCK_BYTES]
            origins=anchors.get(key, ())
            anchors_seen += len(origins)
            for ordinal, source_offset in origins:
                if not 0 <= ordinal < len(sources):
                    raise ValueError("corrupt private candidate index ordinal")
                source,region=sources[ordinal]
                if (source_offset >= BLOCK_BYTES and offset >= BLOCK_BYTES):
                    prev=source[source_offset-BLOCK_BYTES:source_offset]
                    if prev in anchors and prev == row[offset-BLOCK_BYTES:offset]:
                        continue
                length=0
                while (source_offset+(length+1)*BLOCK_BYTES <= len(source) and
                        offset+(length+1)*BLOCK_BYTES <= row_size and
                        source[source_offset+length*BLOCK_BYTES:
                               source_offset+(length+1)*BLOCK_BYTES]
                        == row[offset+length*BLOCK_BYTES:
                               offset+(length+1)*BLOCK_BYTES]):
                    length+=1
                if length < minimum_contiguous_blocks:
                    continue
                total+=1
                if len(matches) < max_run_samples:
                    span=source[source_offset:source_offset+length*BLOCK_BYTES]
                    matches.append({
                        "candidate_stream_ordinal": ordinal,
                        "graphics_region_index": region,
                        "source_offset_bytes": source_offset,
                        "a0_destination_x_words": global_x,
                        "a0_destination_y": y+row_index,
                        "a0_payload_row_index": row_index,
                        "a0_row_offset_bytes": offset,
                        "matched_contiguous_64byte_blocks": length,
                        "matched_byte_span": len(span),
                        "run_sha256": hashlib.sha256(span).hexdigest(),
                        "original_gp0_packet_provenance_unverified": True,
                    })
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_GP0_A0_DECODED_SOURCE_BYTE_RUN_MATCH",
        "a0_destination_x_words": x,
        "a0_destination_y": y,
        "a0_width_u16_words": width,
        "a0_height_rows": height,
        "a0_effective_pixel_bytes": len(payload),
        "a0_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "a0_rows_considered": rows_scanned,
        "aligned_anchor_positions_scanned": aligned_positions_scanned,
        "candidate_anchor_occurrences": anchors_seen,
        "matching_decoded_stream_run_count": total,
        "reported_run_sample_count": len(matches),
        "sample_truncated": total > len(matches),
        "run_samples": matches,
        "interpretation": {
            "direct_a0_payload_byte_equality_not_postframe_occurrence": True,
            "source_to_uploaded_pixel_layout_not_authentically_verified": True,
            "matched_bytes_not_authentication_of_original_gpu_packet": True,
            "a0_payload_not_proof_that_textured_draw_sampled_these_words": True,
            "clut_and_visible_map_geometry_unverified": True,
            "raw_disc_data_packet_words_and_pixels_not_exported": True,
            "all_metadata_and_sha256_fingerprints_owner_private": True,
        }
    }
