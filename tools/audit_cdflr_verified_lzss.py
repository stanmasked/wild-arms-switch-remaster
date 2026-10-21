#!/usr/bin/env python3
"""Metadata-only validation of all compressed CDFLR sprite/texture candidates.

Original CDFLR.BIN is held locally by its owner; never add it or the
decompressed game output to public GitHub, CI, or build artifacts.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from wa1_lzss import LZSSDecodeError, decode_wa1_lzss

SLOT_BYTES = 0x3A000
MAX_SLOTS = 1024
INDICES = tuple(range(43, 58, 2))


def audit_cdflr_lzss(path, *, slot_bytes=SLOT_BYTES):
    path = Path(path)
    if type(slot_bytes) is not int or not 512 <= slot_bytes <= 4*1024*1024 or slot_bytes % 4:
        raise ValueError("invalid fixed record geometry")
    size = path.stat().st_size
    if size <= 0 or size % slot_bytes:
        raise ValueError("source size is not an exact number of fixed records")
    count = size // slot_bytes
    if count > MAX_SLOTS:
        raise ValueError("too many fixed records")
    successes = 0
    bounded_ok = 0
    last_ok = 0
    problems = []
    consumed_by_index = {index: [] for index in INDICES}
    unused_by_index = {index: [] for index in INDICES}
    content_hashes = {index: set() for index in INDICES}
    with path.open("rb") as source:
        for slot in range(count):
            record = source.read(slot_bytes)
            if len(record) != slot_bytes:
                raise ValueError("truncated record")
            pointers = struct.unpack_from("<58I", record)
            base = pointers[0] - 256
            if base % 4 or not 0x80000000 <= base < 0x80200000:
                raise ValueError(f"slot {slot}: invalid RAM-like pointer base")
            offsets = [p-base for p in pointers]
            if (offsets[0] != 256 or offsets[-1] + 4 > slot_bytes or
                    any(b <= a for a, b in zip(offsets, offsets[1:]))):
                raise ValueError(f"slot {slot}: bad pointer order/bound")
            if any(p % 4 or not 0x80000000 <= p < 0x80200000 for p in pointers):
                raise ValueError(f"slot {slot}: invalid PS1 pointer")
            for index in INDICES:
                start=offsets[index]
                end=offsets[index+1] if index < 57 else slot_bytes
                if end-start < 4:
                    raise ValueError(f"slot {slot}: stream region under 4 bytes")
                encoded=record[start:end]
                try:
                    decoded, consumed=decode_wa1_lzss(encoded, max_output=0x8000)
                except LZSSDecodeError as exc:
                    problems.append({"slot": slot, "index": index,
                                     "status": "INCOMPLETE_OR_BAD_STREAM",
                                     "reason": str(exc)})
                    continue
                if len(decoded)!=0x8000:
                    problems.append({"slot":slot,"index":index,
                                     "status":"WRONG_OUTPUT_LENGTH"})
                    continue
                unused=end-start-consumed
                if index < 57 and unused>3:
                    problems.append({"slot":slot,"index":index,
                                     "status":"ENCODED_BOUNDARY_MISMATCH",
                                     "extra_bytes":unused})
                    continue
                successes+=1
                bounded_ok+=int(index<57)
                last_ok+=int(index==57)
                consumed_by_index[index].append(consumed)
                unused_by_index[index].append(unused)
                content_hashes[index].add(hashlib.sha256(decoded).hexdigest())
    return {
        "schema": 1,
        "kind": "WILD_ARMS_CDFLR_VERIFIED_LZSS_AUDIT",
        "source_name":path.name,
        "source_size_bytes":size,
        "slot_bytes":slot_bytes,
        "slot_count":count,
        "candidate_stream_count":count*len(INDICES),
        "decoded_exact_0x8000_stream_count":successes,
        "next_pointer_bounded_valid_count":bounded_ok,
        "last_upper_bounded_valid_count":last_ok,
        "exceptions":problems,
        "per_region":[
            {"pointer_index":idx,
             "valid_streams":len(consumed_by_index[idx]),
             "unique_decoded_hashes":len(content_hashes[idx]),
             "compressed_consumed_bytes_min":min(consumed_by_index[idx],default=None),
             "compressed_consumed_bytes_max":max(consumed_by_index[idx],default=None),
             "unused_region_bytes_min":min(unused_by_index[idx],default=None),
             "unused_region_bytes_max":max(unused_by_index[idx],default=None),
             "last_region_item_size_is_not_automatically_slot_remainder":idx==57}
            for idx in INDICES],
        "interpretation":{
            "codec_follows_open_source_wa1tools_reference":True,
            "first_two_verified_icon_sheets_from_slot_zero":True,
            "last_section_exception_requires_preservation":True,
            "textures_not_assigned_to_maps_without_loader_evidence":True,
            "no_original_decompressed_bytes_emitted":True
        }
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("resource",type=Path,help="private original CDFLR.BIN")
    ap.add_argument("--slot-bytes",type=lambda s:int(s,0),default=SLOT_BYTES)
    args=ap.parse_args()
    print(json.dumps(audit_cdflr_lzss(args.resource,slot_bytes=args.slot_bytes),
                     indent=2,sort_keys=True))


if __name__=="__main__":
    main()
