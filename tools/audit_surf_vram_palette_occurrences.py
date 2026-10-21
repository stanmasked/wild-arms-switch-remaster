#!/usr/bin/env python3
"""PRIVATE Surf Village 16-word palette candidates vs raw original PS1 VRAM.

A byte-exact 16-word match at a possible 4bpp CLUT grid coordinate is only
a MEMORY OCCURRENCE. It is not evidence of GPU use, stream-to-bank assignment,
scene placement, transparency, or a PS1 framebuffer match.

No disc bytes, palette words, pixels, VRAM bytes or source screenshots are
included in output. Keep CDSTG.BIN and VRAM captures on the owner's private disk.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

from audit_surf_palette_rows import read_private_candidates

VRAM_WIDTH_WORDS = 1024
VRAM_HEIGHT = 512
VRAM_BYTES = VRAM_WIDTH_WORDS * VRAM_HEIGHT * 2
PALETTE_WORDS = 16
CLUT_X_ALIGNMENT_WORDS = 16
ROW_BYTES = PALETTE_WORDS * 2


def _row_filter(raw, minimum_distinct_nonzero):
    """Guard against ubiquitous blank/low-information false positives."""
    words = struct.unpack("<16H", raw)
    if all(word == 0 for word in words):
        return "ALL_ZERO"
    if len({word for word in words if word != 0}) < minimum_distinct_nonzero:
        return "LOW_DISTINCT_NONZERO"
    return None


def match_palette_rows_to_private_vram(
        cdstg_path, vram_path, *, map_index=2,
        minimum_distinct_nonzero=3, max_position_samples=16,
        **private_map_geometry):
    """Return metadata-only candidate memory occurrences, not confirmed CLUTs.

    Expects precisely 1024x512 little-endian 16-bit PS1 VRAM words, *not*
    RGBA screenshots, partial captures or opaque emulator savestates.
    """
    if (type(minimum_distinct_nonzero) is not int
            or not 1 <= minimum_distinct_nonzero <= 16):
        raise ValueError("minimum_distinct_nonzero must be in 1..16")
    if (type(max_position_samples) is not int
            or not 1 <= max_position_samples <= 64):
        raise ValueError("max_position_samples must be in 1..64")
    vram_path = Path(vram_path)
    if vram_path.stat().st_size != VRAM_BYTES:
        raise ValueError("VRAM must be exactly 1024x512 little-endian u16 words")
    vram = vram_path.read_bytes()
    if len(vram) != VRAM_BYTES:
        raise ValueError("VRAM changed length while reading")

    private = read_private_candidates(
        cdstg_path, map_index=map_index, **private_map_geometry)
    candidates = defaultdict(list)
    rejected = defaultdict(int)
    total_rows = 0
    for bank_index, bank in enumerate(private["candidate_banks"]):
        for row_index in range(16):
            raw = bank[row_index*ROW_BYTES:(row_index+1)*ROW_BYTES]
            total_rows += 1
            exclusion = _row_filter(raw, minimum_distinct_nonzero)
            if exclusion:
                rejected[exclusion] += 1
                continue
            candidates[raw].append({
                "candidate_bank_index": bank_index,
                "candidate_row_index": row_index,
            })

    # VRAM is arranged in 1024 16-bit WORDS per scanline, not 1024 bytes.
    # A hypothetical 4bpp CLUT begins on an x coordinate divisible by 16.
    # Never scan across a VRAM row boundary or at odd word-grid columns.
    found = {}
    for y in range(VRAM_HEIGHT):
        base = y * VRAM_WIDTH_WORDS * 2
        for x in range(0, VRAM_WIDTH_WORDS-PALETTE_WORDS+1,
                       CLUT_X_ALIGNMENT_WORDS):
            start = base + x*2
            raw = vram[start:start+ROW_BYTES]
            if raw not in candidates:
                continue
            entry = found.setdefault(raw, {"match_count": 0, "positions": []})
            entry["match_count"] += 1
            if len(entry["positions"]) < max_position_samples:
                entry["positions"].append({"x_words": x, "y": y})

    rows = []
    for raw, references in sorted(
            candidates.items(), key=lambda item: hashlib.sha256(item[0]).hexdigest()):
        occurrence = found.get(raw, {"match_count": 0, "positions": []})
        rows.append({
            "candidate_row_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_bank_row_references": references,
            "matching_grid_position_count": occurrence["match_count"],
            "matching_grid_position_sample": occurrence["positions"],
            "position_sample_truncated":
                occurrence["match_count"] > len(occurrence["positions"]),
        })

    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_SURF_VRAM_PALETTE_MEMORY_OCCURRENCES",
        "map_index": private["map_index"],
        "vram_layout": "1024x512_le_u16_words",
        "vram_sha256": hashlib.sha256(vram).hexdigest(),
        "candidate_bank_count": len(private["candidate_banks"]),
        "validated_bounded_lzss_stream_count": len(private["verified_streams"]),
        "candidate_row_count": total_rows,
        "eligible_byte_distinct_row_count": len(rows),
        "eligible_bank_row_reference_count": sum(
            len(row["candidate_bank_row_references"]) for row in rows),
        "excluded_all_zero_rows": rejected["ALL_ZERO"],
        "excluded_low_distinct_nonzero_rows": rejected["LOW_DISTINCT_NONZERO"],
        "rows_with_at_least_one_memory_occurrence": sum(
            row["matching_grid_position_count"] > 0 for row in rows),
        "candidate_rows": rows,
        "interpretation": {
            "raw_vram_and_palette_words_not_exported": True,
            "exact_grid_occurrences_are_not_verified_clut_use": True,
            "palette_bank_to_stream_assignment_unverified": True,
            "palette_row_to_sprite_or_tile_assignment_unverified": True,
            "texture_page_and_gpu_draw_commands_unverified": True,
            "ps1_stp_alpha_and_zero_index_semantics_unverified": True,
            "no_original_framebuffer_comparison": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_cdstg", type=Path)
    parser.add_argument("private_vram_u16le", type=Path)
    parser.add_argument("--map-index", type=int, default=2)
    parser.add_argument("--minimum-distinct-nonzero", type=int, default=3)
    parser.add_argument("--max-position-samples", type=int, default=16)
    args = parser.parse_args()
    report = match_palette_rows_to_private_vram(
        args.private_cdstg, args.private_vram_u16le,
        map_index=args.map_index,
        minimum_distinct_nonzero=args.minimum_distinct_nonzero,
        max_position_samples=args.max_position_samples)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
