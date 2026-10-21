#!/usr/bin/env python3
"""Stage436: verify a PRIVATE extracted WA1 CDSTG against its original raw disc.

Compares all 76,021,760 bytes to the ISO9660 source extent, then independently
checks Surf Village map #2 candidate-bank and bounded WA1-LZSS structure.
Reports only hashes, counts, sector geometry and explicit uncertainty flags.
Never uploads or writes any copyrighted disc, map, palette or image bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_surf_palette_rows import audit_palette_candidates
from extract_private_cdstg_from_cue_bin import (
    CDSTG_BYTES, RAW_SECTOR, RawMode2ISO, read_single_track_cue,
)

SHA_BLOCK = 1024 * 1024


def _identity(path):
    stats = Path(path).stat()
    return (stats.st_dev, stats.st_ino, stats.st_size, stats.st_mtime_ns)


def _file_sha256(path, expected_size):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("extracted CDSTG must be a regular private file")
    if path.stat().st_size != expected_size:
        raise ValueError("extracted CDSTG has unexpected geometry")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(SHA_BLOCK)
            if not chunk:
                break
            count += len(chunk)
            if count > expected_size:
                raise ValueError("extracted CDSTG became longer during read")
            digest.update(chunk)
    if count != expected_size:
        raise ValueError("extracted CDSTG became truncated during read")
    return digest.hexdigest()


def _extent_sha256(disc, record):
    digest = hashlib.sha256()
    total = 0
    for raw in disc._extent_bytes(record["start"], record["length"]):
        total += len(raw)
        digest.update(raw)
    if total != record["length"]:
        raise ValueError("raw disc extent read incomplete")
    return digest.hexdigest()


def _trusted_structural_summary(report, map_index):
    """Validate decoder's basic contract before reporting aggregated counts."""
    fields = (
        "candidate_512_byte_bank_count", "verified_bounded_lzss_stream_count",
        "candidate_16_color_row_count", "byte_distinct_palette_row_count",
        "all_zero_candidate_row_count",
    )
    if (not isinstance(report, dict) or
            type(report.get("map_index")) is not int or
            report["map_index"] != map_index or
            any(type(report.get(key)) is not int for key in fields)):
        raise ValueError("Surf Village structural analyzer returned invalid summary")
    banks, streams, rows, distinct, blank = [report[k] for k in fields]
    if not (1 <= banks <= 32 and 1 <= streams <= 64 and
            rows == banks * 16 and 0 <= distinct <= rows and
            0 <= blank <= rows):
        raise ValueError("Surf Village palette/stream count invariants failed")
    return {key: report[key] for key in fields}


def audit_private_cdstg_disc_source(
        cue_path, extracted_cdstg, *, map_index=2,
        expected_extracted_bytes=CDSTG_BYTES,
        expected_raw_sector_count=None, expected_banks=7,
        expected_streams=7):
    """Double-source integrity and independently bounded map structure.

    A successful report is provenance/integrity evidence, NOT proof of the
    original release hash, original GPU-rendered colors or scene authenticity.
    """
    if (type(map_index) is not int or not 0 <= map_index < 128 or
            type(expected_extracted_bytes) is not int or
            not 1 <= expected_extracted_bytes <= CDSTG_BYTES or
            expected_raw_sector_count is not None and (
                type(expected_raw_sector_count) is not int or
                expected_raw_sector_count < 20)):
        raise ValueError("invalid audit map / source size parameters")
    for name, value in (("palette banks", expected_banks),
                        ("bounded streams", expected_streams)):
        if type(value) is not int or not 1 <= value <= 64:
            raise ValueError("invalid expected " + name)
    source = read_single_track_cue(cue_path)
    source_before = _identity(source)
    target_before = _identity(extracted_cdstg)
    with RawMode2ISO(source) as disc:
        if (expected_raw_sector_count is not None and
                disc.sector_count != expected_raw_sector_count):
            raise ValueError("raw source sector count does not match requested evidence")
        record = disc.find_cdstg(expected_size=expected_extracted_bytes)
        source_hash = _extent_sha256(disc, record)
        source_sectors = disc.sector_count
        original_lba = record["start"]

    extracted_hash = _file_sha256(extracted_cdstg, expected_extracted_bytes)
    if source_hash != extracted_hash:
        raise ValueError("private CDSTG does not byte-match the original CUE/BIN extent")

    # This operation may decompress the map in memory only. It never returns
    # or persists raw decoded map bytes in the report.
    structural = _trusted_structural_summary(
        audit_palette_candidates(extracted_cdstg, map_index=map_index),
        map_index)
    if (structural["candidate_512_byte_bank_count"] != expected_banks or
            structural["verified_bounded_lzss_stream_count"] != expected_streams):
        raise ValueError("CDSTG map structure differs from expected original observations")

    if source_before != _identity(source) or target_before != _identity(extracted_cdstg):
        raise ValueError("source BIN or private extraction changed during verification")
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_CDSTG_DISC_SOURCE_MAP_COHERENCE",
        "raw_sector_bytes": RAW_SECTOR,
        "original_cue_track_type": "MODE2/2352",
        "raw_source_sector_count": source_sectors,
        "cdstg_iso_extent_start_lba": original_lba,
        "cdstg_bytes": expected_extracted_bytes,
        "source_cd_resource_sha256": source_hash,
        "private_extraction_sha256": extracted_hash,
        "source_and_extracted_bytes_identical": True,
        "map_index": map_index,
        **structural,
        "expected_candidate_palette_banks": expected_banks,
        "expected_bounded_lzss_streams": expected_streams,
        "interpretation": {
            "raw_disc_and_private_extraction_checked_byte_exact": True,
            "structural_map_validation_was_run_privately": True,
            "original_disc_release_hash_not_independently_authenticated": True,
            "matching_iso_bytes_not_a_gpu_frame_capture": True,
            "palette_row_to_texture_assignment_unverified": True,
            "raw_disc_palette_and_map_pixels_not_exported": True,
            "metadata_and_hashes_also_private": True,
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_cue", type=Path)
    ap.add_argument("private_extracted_cdstg", type=Path)
    ap.add_argument("--map-index", type=int, default=2)
    ap.add_argument("--expected-raw-sectors", type=int)
    args = ap.parse_args()
    result = audit_private_cdstg_disc_source(
        args.private_cue, args.private_extracted_cdstg,
        map_index=args.map_index,
        expected_raw_sector_count=args.expected_raw_sectors)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
