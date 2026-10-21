#!/usr/bin/env python3
"""PRIVATE comparison of two independently captured paused Surf Village VRAMs.

Correlates Stage426 candidate 16-word rows across two Stage430 verified
private captures at 16-word aligned *potential* 4bpp CLUT coordinates.
Identical memory bytes alone cannot authenticate a scene, a GPU packet,
or a palette actually sampled during a PS1 draw. Never commit raw data.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from audit_surf_palette_rows import read_private_candidates
from audit_surf_vram_palette_occurrences import _row_filter
from capture_private_pcsx_redux_vram import (
    MANIFEST_KIND, RAW_VRAM_BYTES, _validate_basename,
)

VRAM_WIDTH_WORDS = 1024
VRAM_HEIGHT = 512
GRID_WORDS = 16
PALETTE_BYTES = 32
MAX_MANIFEST_BYTES = 16384


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate capture manifest JSON field")
        out[key] = value
    return out


def read_verified_paused_capture(directory, basename):
    """Read snapshot ONCE and hash the actual bytes used for comparison."""
    _validate_basename(basename)
    root = Path(directory)
    manifest_path = root / (basename + ".capture.json")
    raw_path = root / (basename + ".u16le.bin")
    if manifest_path.is_symlink() or raw_path.is_symlink():
        raise ValueError("symlink capture files are not accepted")
    if not 0 < manifest_path.stat().st_size <= MAX_MANIFEST_BYTES:
        raise ValueError("invalid capture manifest length")
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"),
                              object_pairs_hook=_no_duplicates)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid capture manifest JSON") from exc
    expected = {
        "schema": 1,
        "kind": MANIFEST_KIND,
        "source": "PCSX-Redux localhost GET /api/v1/gpu/vram/raw",
        "vram_filename": basename + ".u16le.bin",
        "manifest_filename": basename + ".capture.json",
        "bytes": RAW_VRAM_BYTES,
        "snapshot_read_count": 2,
        "execution_flow_read_count": 3,
        "api_reported_running_false_in_all_three_observations": True,
        "two_read_bytes_identical": True,
        "emulator_was_paused_at_capture_unverified": True,
        "game_map_and_frame_number_unverified": True,
        "not_evidence_of_runtime_clut_selection": True,
    }
    if (not isinstance(document, dict) or any(
            type(document.get(key)) is not type(value)
            or document.get(key) != value for key, value in expected.items())):
        raise ValueError("capture is not an intact Stage430 paused double-read")
    digest = document.get("vram_sha256")
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("capture manifest has invalid SHA-256")
    label = document.get("operator_scene_label")
    if type(label) is not str or not 1 <= len(label) <= 160:
        raise ValueError("capture manifest missing a valid operator label")
    if raw_path.stat().st_size != RAW_VRAM_BYTES:
        raise ValueError("capture VRAM length invalid")
    raw = raw_path.read_bytes()
    if len(raw) != RAW_VRAM_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("capture VRAM hash mismatch or file changed")
    return {"bytes": raw, "sha256": digest, "operator_scene_label": label}


def _indexed_clut_candidates(banks, *, minimum_distinct_nonzero=3):
    if (type(minimum_distinct_nonzero) is not int
            or not 1 <= minimum_distinct_nonzero <= 16):
        raise ValueError("minimum_distinct_nonzero must be within 1..16")
    raw_to_sources = defaultdict(list)
    ignored = Counter()
    for bank_index, bank in enumerate(banks):
        if not isinstance(bank, bytes) or len(bank) != 512:
            raise ValueError("candidate palette bank must be exactly 512 bytes")
        for row_index in range(16):
            candidate = bank[row_index*PALETTE_BYTES:(row_index+1)*PALETTE_BYTES]
            reason = _row_filter(candidate, minimum_distinct_nonzero)
            if reason:
                ignored[reason] += 1
            else:
                raw_to_sources[candidate].append({
                    "candidate_bank_index": bank_index, "candidate_row_index": row_index})
    return raw_to_sources, ignored


def _find_candidate_positions(raw, candidates):
    if len(raw) != RAW_VRAM_BYTES:
        raise ValueError("VRAM snapshot length invalid")
    located = defaultdict(set)
    for y in range(VRAM_HEIGHT):
        row_start = y * VRAM_WIDTH_WORDS * 2
        for x in range(0, VRAM_WIDTH_WORDS, GRID_WORDS):
            offset = row_start + x*2
            chunk = raw[offset:offset+PALETTE_BYTES]
            if chunk in candidates:
                located[chunk].add((y,x))
    return located


def compare_private_paused_snapshots(first, second, banks, *,
                                     minimum_distinct_nonzero=3,
                                     max_position_samples=16):
    """In-memory algorithm: metadata only; never emits raw VRAM or palette words."""
    if type(max_position_samples) is not int or not 1 <= max_position_samples <= 64:
        raise ValueError("max_position_samples must be within 1..64")
    raw_a, raw_b = first["bytes"], second["bytes"]
    if len(raw_a) != RAW_VRAM_BYTES or len(raw_b) != RAW_VRAM_BYTES:
        raise ValueError("both raw captures must be 1048576 bytes")
    rows, ignored = _indexed_clut_candidates(
        banks, minimum_distinct_nonzero=minimum_distinct_nonzero)
    locations_a = _find_candidate_positions(raw_a, rows)
    locations_b = _find_candidate_positions(raw_b, rows)
    results = []
    classes = Counter()
    for palette, references in sorted(
            rows.items(), key=lambda item: hashlib.sha256(item[0]).hexdigest()):
        a = locations_a.get(palette, set())
        b = locations_b.get(palette, set())
        common = a & b
        if common:
            cls = "COMMON_COORDINATES"
        elif a and b:
            cls = "BOTH_PRESENT_DIFFERENT_COORDINATES"
        elif a:
            cls = "FIRST_ONLY"
        elif b:
            cls = "SECOND_ONLY"
        else:
            cls = "ABSENT_BOTH"
        classes[cls] += 1
        results.append({
            "candidate_row_sha256": hashlib.sha256(palette).hexdigest(),
            "candidate_bank_row_references": references,
            "classification": cls,
            "first_grid_occurrence_count": len(a),
            "second_grid_occurrence_count": len(b),
            "common_coordinate_count": len(common),
            "common_coordinate_samples": [
                {"x_words": x, "y": y}
                for y, x in sorted(common)[:max_position_samples]],
            "common_coordinate_samples_truncated":
                len(common) > max_position_samples,
        })
    changed_words = sum(raw_a[off:off+2] != raw_b[off:off+2]
                        for off in range(0, RAW_VRAM_BYTES, 2))
    changed_16word_cells = sum(raw_a[off:off+PALETTE_BYTES] !=
                               raw_b[off:off+PALETTE_BYTES]
                               for off in range(0, RAW_VRAM_BYTES, PALETTE_BYTES))
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_SURF_TWO_PAUSED_VRAM_CANDIDATE_CORRELATION",
        "vram_a_sha256": hashlib.sha256(raw_a).hexdigest(),
        "vram_b_sha256": hashlib.sha256(raw_b).hexdigest(),
        "snapshots_byte_identical": raw_a == raw_b,
        "changed_u16_word_count": changed_words,
        "changed_16word_grid_cell_count": changed_16word_cells,
        "total_16word_grid_cells": RAW_VRAM_BYTES // PALETTE_BYTES,
        "candidate_bank_count": len(banks),
        "eligible_distinct_candidate_row_count": len(rows),
        "excluded_all_zero_rows": ignored["ALL_ZERO"],
        "excluded_low_distinct_nonzero_rows": ignored["LOW_DISTINCT_NONZERO"],
        "row_classes": dict(sorted(classes.items())),
        "candidate_rows": results,
        "interpretation": {
            "both_sources_were_stage430_double_read_captures": True,
            "matching_operator_labels_do_not_prove_scene_identity": True,
            "common_grid_coordinate_not_proof_of_gpu_clut_use": True,
            "temporal_draw_time_palette_unverified": True,
            "clut_cache_and_texture_page_state_unverified": True,
            "row_to_texture_and_tile_mapping_unverified": True,
            "no_original_color_words_or_pixels_exported": True,
        },
    }


def audit_private_surf_capture_pair(
        cdstg, capture_directory, first_basename, second_basename,
        *, map_index=2, max_position_samples=16,
        minimum_distinct_nonzero=3, **geometry):
    _validate_basename(first_basename)
    _validate_basename(second_basename)
    if first_basename == second_basename:
        raise ValueError("comparison requires two distinct capture basenames")
    first = read_verified_paused_capture(capture_directory, first_basename)
    second = read_verified_paused_capture(capture_directory, second_basename)
    if first["operator_scene_label"] != second["operator_scene_label"]:
        raise ValueError("operator scene labels differ; do not compare as one scene")
    private = read_private_candidates(cdstg, map_index=map_index, **geometry)
    report = compare_private_paused_snapshots(
        first, second, private["candidate_banks"],
        max_position_samples=max_position_samples,
        minimum_distinct_nonzero=minimum_distinct_nonzero)
    return {
        "map_index": private["map_index"],
        "bounded_lzss_stream_count": len(private["verified_streams"]),
        "capture_labels_same_but_not_authenticated": True,
        **report,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_cdstg", type=Path)
    ap.add_argument("private_capture_directory", type=Path)
    ap.add_argument("first_basename")
    ap.add_argument("second_basename")
    ap.add_argument("--map-index", type=int, default=2)
    ap.add_argument("--minimum-distinct-nonzero", type=int, default=3)
    ap.add_argument("--max-position-samples", type=int, default=16)
    args = ap.parse_args()
    report = audit_private_surf_capture_pair(
        args.private_cdstg, args.private_capture_directory,
        args.first_basename, args.second_basename,
        map_index=args.map_index,
        minimum_distinct_nonzero=args.minimum_distinct_nonzero,
        max_position_samples=args.max_position_samples)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
