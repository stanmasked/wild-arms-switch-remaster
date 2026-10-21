#!/usr/bin/env python3
"""Read-only, metadata-only probe for candidate fixed-stride CDSTG records.

Repeated markers and RAM-like words are *not* a verified gameplay format.
No raw payload, strings, textures or game dialogue are printed or exported.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

DEFAULT_RECORD_BYTES = 593_920
DEFAULT_MARKER = b"Sony"
DEFAULT_MARKER_OFFSET = 0x3C
MAX_HEADER_BYTES = 4096
MAX_RECORDS = 100000


def inspect_records(path, record_bytes=DEFAULT_RECORD_BYTES,
                    marker=DEFAULT_MARKER, marker_offset=DEFAULT_MARKER_OFFSET):
    path = Path(path)
    if type(record_bytes) is not int or record_bytes < 64:
        raise ValueError("record_bytes must be an integer >= 64")
    if not isinstance(marker, bytes) or not marker or len(marker) > MAX_HEADER_BYTES:
        raise ValueError("marker must be 1..4096 bytes")
    if type(marker_offset) is not int or marker_offset < 0 or marker_offset + len(marker) > record_bytes:
        raise ValueError("marker is outside a record")
    size = path.stat().st_size
    if size == 0 or size % record_bytes:
        raise ValueError("file size is not a nonempty whole number of records")
    count = size // record_bytes
    if count > MAX_RECORDS:
        raise ValueError("too many records for a bounded metadata report")
    header_length = max(12, marker_offset + len(marker))
    if header_length > MAX_HEADER_BYTES:
        raise ValueError("marker beyond maximum header inspection")
    records = []
    marker_matches = 0
    ram_word0 = 0
    ram_word8 = 0
    digests = set()
    with path.open("rb") as source:
        for index in range(count):
            sha256 = hashlib.sha256()
            header = b""
            remaining = record_bytes
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("file truncated while reading records")
                if len(header) < header_length:
                    header += chunk[:header_length - len(header)]
                sha256.update(chunk)
                remaining -= len(chunk)
            word0 = struct.unpack_from("<I", header, 0)[0]
            word8 = struct.unpack_from("<I", header, 8)[0]
            marker_match = header[marker_offset:marker_offset + len(marker)] == marker
            kseg0_0 = 0x80000000 <= word0 < 0x80200000
            kseg0_8 = 0x80000000 <= word8 < 0x80200000
            marker_matches += int(marker_match)
            ram_word0 += int(kseg0_0)
            ram_word8 += int(kseg0_8)
            digest = sha256.hexdigest()
            digests.add(digest)
            records.append({
                "index": index,
                "start_offset": index * record_bytes,
                "sha256": digest,
                "marker_match": marker_match,
                "word0_ps1_kseg0_2mb_like": kseg0_0,
                "word8_ps1_kseg0_2mb_like": kseg0_8,
            })
    return {
        "schema": 1,
        "kind": "FIXED_STRIDE_RECORD_PROBE",
        "source_name": path.name,
        "source_size_bytes": size,
        "record_bytes": record_bytes,
        "record_count": count,
        "marker_offset": marker_offset,
        "marker_ascii": marker.decode("ascii", "replace"),
        "marker_matches": marker_matches,
        "marker_exceptions": [r["index"] for r in records if not r["marker_match"]],
        "word0_ram_like_count": ram_word0,
        "word8_ram_like_count": ram_word8,
        "unique_record_hash_count": len(digests),
        "records": records,
        "interpretation": {
            "status": "STRIDE_AND_MARKER_METADATA_ONLY",
            "gameplay_role_is_not_verified": True,
            "ram_like_words_are_not_proven_pointers": True,
            "copyrighted_payload_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="private local resource file")
    parser.add_argument("--record-bytes", type=int, default=DEFAULT_RECORD_BYTES)
    parser.add_argument("--marker-offset", type=int, default=DEFAULT_MARKER_OFFSET)
    parser.add_argument("--marker", default="Sony", help="ASCII marker")
    args = parser.parse_args()
    print(json.dumps(inspect_records(args.path, args.record_bytes,
                                     args.marker.encode("ascii"), args.marker_offset),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
