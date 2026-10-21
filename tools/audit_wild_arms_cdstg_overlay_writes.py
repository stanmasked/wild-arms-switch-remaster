#!/usr/bin/env python3
"""Metadata-only static constant-store scan of CDSTG trimmed PS-X EXE overlays.

Only record headers matching a strict executable-like pattern are scanned.
Exceptional records remain unclassified. No original bytes are emitted.
"""
import argparse
import json
import struct
from pathlib import Path

from audit_wild_arms_slot_writes import scan_instruction_words, TARGET

RECORD_BYTES = 593_920
EXPECTED_RECORDS = 128
HEADER_BYTES = 0x40
MAX_RECORDS = 128


def audit_overlays(path, record_bytes=RECORD_BYTES, expected_records=EXPECTED_RECORDS):
    path = Path(path)
    if type(record_bytes) is not int or record_bytes < HEADER_BYTES + 4 or record_bytes % 4:
        raise ValueError("record_bytes must be aligned and large enough for header")
    if type(expected_records) is not int or not 1 <= expected_records <= MAX_RECORDS:
        raise ValueError("expected_records out of safe bounds")
    size = path.stat().st_size
    if size != record_bytes * expected_records:
        raise ValueError("CDSTG size does not match the explicit record geometry")

    records_scanned = 0
    exceptions = []
    candidate_stores = []
    unresolved_immediates = []
    total_resets = 0
    with path.open("rb") as source:
        for index in range(expected_records):
            record = source.read(record_bytes)
            if len(record) != record_bytes:
                raise ValueError("record truncated")
            entry, gp, load_address, text_bytes = struct.unpack_from("<4I", record, 0)
            stack_address = struct.unpack_from("<I", record, 0x20)[0]
            overlay_like = (
                record[0x3C:0x40] == b"Sony" and gp == 0 and
                0x80000000 <= load_address < 0x80200000 and
                0 < text_bytes <= record_bytes - HEADER_BYTES and text_bytes % 4 == 0 and
                load_address <= entry < load_address + text_bytes and
                load_address + text_bytes <= 0x80200000 and
                entry % 4 == 0 and stack_address == 0x801FFFF0
            )
            if not overlay_like:
                exceptions.append(index)
                continue
            words = struct.unpack_from("<" + str(text_bytes // 4) + "I",
                                       record, HEADER_BYTES)
            scan = scan_instruction_words(words, TARGET)
            total_resets += scan["flow_resets_after_control_transfer"]
            for hit in scan["computed_constant_target_store_sites"]:
                candidate_stores.append({
                    "record_index": index,
                    "offset_in_record": hit["file_offset"] - 0x800 + HEADER_BYTES,
                    "operation": hit["operation"],
                })
            for offset in scan["unknown_base_same_low_immediate_sites"]:
                unresolved_immediates.append({
                    "record_index": index,
                    "offset_in_record": offset - 0x800 + HEADER_BYTES,
                })
            records_scanned += 1
    return {
        "schema": 1,
        "kind": "WILD_ARMS_CDSTG_OVERLAY_CONSTANT_STORE_AUDIT",
        "source_name": path.name,
        "source_size_bytes": size,
        "record_bytes": record_bytes,
        "record_count": expected_records,
        "psx_overlay_like_records_scanned": records_scanned,
        "exceptional_record_indices": exceptions,
        "constant_proven_store_site_count": len(candidate_stores),
        "constant_proven_store_sites": candidate_stores,
        "unknown_base_same_low_immediate_count": len(unresolved_immediates),
        "unknown_base_same_low_immediate_sites": unresolved_immediates,
        "flow_reset_count": total_resets,
        "interpretation": {
            "only_potential_overlay_code_scanned": True,
            "no_full_control_flow_or_dynamic_execution": True,
            "zero_matches_cannot_rule_out_runtime_writes": True,
            "exceptional_record_not_discarded": True,
            "original_asset_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="private local CDSTG.BIN")
    args = parser.parse_args()
    print(json.dumps(audit_overlays(args.path), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
