#!/usr/bin/env python3
"""Private CDSTG decoded-stream vs PS1 VRAM contiguous-row occurrence audit.

Only evidence of identical BYTE RUNS in a private raw VRAM snapshot.
No claim that a source stream was uploaded by GP0, bound to a texture
page, sampled by a polygon, or used to draw a Surf Village landmark.
Never output original graphics or VRAM bytes in JSON.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from audit_surf_palette_rows import read_private_candidates
from audit_surf_vram_palette_occurrences import VRAM_BYTES

VRAM_ROW_BYTES = 1024 * 2
VRAM_HEIGHT = 512
BLOCK_BYTES = 64
VRAM_GRID_BYTES = 32  # 16 PS1 u16 words
MAX_DECODED_BYTES = 0x10000
MAX_STREAMS = 64
MAX_ANCHOR_FANOUT = 16
MAX_RUN_SAMPLES = 256


def _qualifies_anchor(block, minimum_distinct_bytes, minimum_nonzero_bytes):
    return (len(block) == BLOCK_BYTES
            and len(set(block)) >= minimum_distinct_bytes
            and sum(value != 0 for value in block) >= minimum_nonzero_bytes)


def match_decoded_stream_runs(
        streams, vram, *, minimum_contiguous_blocks=3,
        minimum_distinct_bytes=12, minimum_nonzero_bytes=32,
        max_run_samples=32):
    """Find contiguous 64-byte source runs inside one aligned VRAM scanline.

    The source is read at 64-byte-aligned offsets. A VRAM hit starts
    at an x coordinate divisible by 16 16-bit words. An accepted run
    must contain N *consecutive* 64-byte blocks in exactly the same
    byte order, with no crossing of VRAM scanline boundaries.
    """
    if (type(vram) is not bytes or len(vram) != VRAM_BYTES
            or not isinstance(streams, list) or len(streams) > MAX_STREAMS
            or any(type(value) is not int for value in (
                minimum_contiguous_blocks, minimum_distinct_bytes,
                minimum_nonzero_bytes, max_run_samples))
            or not 2 <= minimum_contiguous_blocks <= 32
            or not 2 <= minimum_distinct_bytes <= 64
            or not 1 <= minimum_nonzero_bytes <= 64
            or not 1 <= max_run_samples <= MAX_RUN_SAMPLES):
        raise ValueError("invalid stream/VRAM matching input or limits")

    selected = []
    index = defaultdict(list)
    skipped_low_information = 0
    total_blocks = 0
    for ordinal, stream in enumerate(streams):
        if type(stream) is not dict:
            raise ValueError("invalid source stream object")
        data = stream.get("decoded")
        region_index = stream.get("graphics_region_index")
        if (type(data) is not bytes or
                not BLOCK_BYTES <= len(data) <= MAX_DECODED_BYTES
                or len(data) % BLOCK_BYTES
                or type(region_index) is not int or region_index < 0):
            raise ValueError("verified source stream requires 64-byte-aligned decoded bytes")
        selected.append(data)
        for offset in range(0, len(data), BLOCK_BYTES):
            block = data[offset:offset+BLOCK_BYTES]
            total_blocks += 1
            if not _qualifies_anchor(
                    block, minimum_distinct_bytes, minimum_nonzero_bytes):
                skipped_low_information += 1
                continue
            index[block].append((ordinal,offset))

    # Very frequent anchors are not discriminatory even when they look
    # diverse; never infer placement from repeated tiles/patterns alone.
    excessive = {key for key, sources in index.items()
                 if len(sources) > MAX_ANCHOR_FANOUT}
    skipped_high_fanout = sum(len(index[key]) for key in excessive)
    for key in excessive:
        del index[key]

    accepted = []
    accepted_total = 0
    candidate_anchor_hits = 0
    x_positions_scanned = 0
    for y in range(VRAM_HEIGHT):
        row_start = y*VRAM_ROW_BYTES
        row = vram[row_start:row_start+VRAM_ROW_BYTES]
        for x_bytes in range(0, VRAM_ROW_BYTES-BLOCK_BYTES+1,
                             VRAM_GRID_BYTES):
            x_positions_scanned += 1
            anchor = row[x_bytes:x_bytes+BLOCK_BYTES]
            origins = index.get(anchor)
            if not origins:
                continue
            candidate_anchor_hits += len(origins)
            for ordinal, source_offset in origins:
                source = selected[ordinal]
                # A run should be reported once at its earliest position.
                # Even if its prior block was low-information, suppress a
                # continuation that would exaggerate placement evidence.
                if (source_offset >= BLOCK_BYTES and x_bytes >= BLOCK_BYTES
                    and source[source_offset-BLOCK_BYTES:source_offset]
                        == row[x_bytes-BLOCK_BYTES:x_bytes]):
                    continue
                extension = 0
                while (source_offset+(extension+1)*BLOCK_BYTES <= len(source)
                       and x_bytes+(extension+1)*BLOCK_BYTES <= VRAM_ROW_BYTES
                       and source[
                           source_offset+extension*BLOCK_BYTES:
                           source_offset+(extension+1)*BLOCK_BYTES]
                       == row[
                           x_bytes+extension*BLOCK_BYTES:
                           x_bytes+(extension+1)*BLOCK_BYTES]):
                    extension += 1
                if extension < minimum_contiguous_blocks:
                    continue
                accepted_total += 1
                if len(accepted) < max_run_samples:
                    sequence = source[
                        source_offset:source_offset+extension*BLOCK_BYTES]
                    accepted.append({
                        "candidate_stream_ordinal": ordinal,
                        "graphics_region_index":
                            streams[ordinal]["graphics_region_index"],
                        "source_offset_bytes": source_offset,
                        "vram_x_words": x_bytes // 2,
                        "vram_y": y,
                        "exact_contiguous_block_count": extension,
                        "exact_byte_span": len(sequence),
                        "byte_span_sha256": hashlib.sha256(sequence).hexdigest(),
                        "source_stream_sha256":
                            hashlib.sha256(source).hexdigest(),
                        "relative_source_to_vram_geometry_unverified": True,
                    })
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_SURF_DECODED_STREAM_VRAM_CONTIGUOUS_RUNS",
        "vram_sha256": hashlib.sha256(vram).hexdigest(),
        "source_stream_count": len(streams),
        "source_64_byte_block_count": total_blocks,
        "source_low_information_anchor_exclusions": skipped_low_information,
        "source_high_fanout_anchor_exclusions": skipped_high_fanout,
        "distinct_eligible_anchor_count": len(index),
        "vram_aligned_positions_scanned": x_positions_scanned,
        "candidate_anchor_hit_count": candidate_anchor_hits,
        "confirmed_byte_identical_run_count": accepted_total,
        "minimum_required_contiguous_blocks": minimum_contiguous_blocks,
        "reported_run_sample_count": len(accepted),
        "run_samples_truncated": accepted_total > len(accepted),
        "run_samples": accepted,
        "interpretation": {
            "run_is_byte_exact_within_one_vram_scanline": True,
            "source_byte_order_retained_without_swizzling": True,
            "stream_to_gpu_texture_page_not_authenticated": True,
            "unmatched_stream_not_proof_of_absence_due_to_layout_or_filtering": True,
            "matched_run_does_not_prove_a_gp0_transfer_or_visible_draw": True,
            "texture_cache_clut_stp_and_source_map_identity_unverified": True,
            "original_stream_bytes_vram_bytes_and_pixels_never_exported": True,
            "metadata_hashes_remain_owner_private": True,
        }
    }


def audit_private_surf_stream_vram(
        private_cdstg, private_vram, *, map_index=2,
        minimum_contiguous_blocks=3, max_run_samples=32):
    path = Path(private_vram)
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size != VRAM_BYTES):
        raise ValueError("private VRAM must be exact 1048576-byte regular file")
    data = path.read_bytes()
    if len(data) != VRAM_BYTES:
        raise ValueError("VRAM length changed during private read")
    original = read_private_candidates(private_cdstg, map_index=map_index)
    result = match_decoded_stream_runs(
        original["verified_streams"], data,
        minimum_contiguous_blocks=minimum_contiguous_blocks,
        max_run_samples=max_run_samples)
    return {
        **result,
        "map_index": original["map_index"],
        "private_palette_bank_count": len(original["candidate_banks"]),
        "source_graphics_pointer_count": original["graphics_pointer_count"],
        "private_decoded_streams_not_emitted": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_cdstg", type=Path)
    parser.add_argument("private_vram_u16le", type=Path)
    parser.add_argument("--map-index", type=int, default=2)
    parser.add_argument("--minimum-contiguous-blocks", type=int, default=3)
    parser.add_argument("--max-run-samples", type=int, default=32)
    args=parser.parse_args()
    print(json.dumps(audit_private_surf_stream_vram(
        args.private_cdstg,args.private_vram_u16le,map_index=args.map_index,
        minimum_contiguous_blocks=args.minimum_contiguous_blocks,
        max_run_samples=args.max_run_samples),indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
