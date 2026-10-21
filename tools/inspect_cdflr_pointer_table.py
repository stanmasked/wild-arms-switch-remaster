#!/usr/bin/env python3
"""Read-only, metadata-only probe for a candidate PS1 RAM pointer table.

Does not decode artwork, scripts or executable data. Source bytes are never
printed. The address-base inference is a hypothesis, not proof of format.
"""
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

PREFIX_BYTES = 256
MAX_ENTRIES = PREFIX_BYTES // 4
MIN_ENTRIES = 2
LOW_RAM = 0x80000000
HIGH_RAM = 0x80200000


def inspect_pointer_table(path):
    path = Path(path)
    file_size = path.stat().st_size
    if file_size < PREFIX_BYTES + 4:
        raise ValueError("file is too small for a 256-byte table and target")
    with path.open("rb") as source:
        prefix = source.read(PREFIX_BYTES)
        addresses = struct.unpack("<64I", prefix)
        count = 0
        while count < MAX_ENTRIES and LOW_RAM <= addresses[count] < HIGH_RAM:
            count += 1
        if count < MIN_ENTRIES:
            raise ValueError("no candidate RAM-address table found")
        if count >= MAX_ENTRIES or addresses[count] != 0:
            raise ValueError("no zero terminator within 256-byte candidate header")
        if any(b != 0 for b in prefix[count * 4:]):
            raise ValueError("nonzero bytes after candidate table terminator")
        table = addresses[:count]
        if any(a % 4 for a in table):
            raise ValueError("candidate pointers are not word-aligned")
        if any(b <= a for a, b in zip(table, table[1:])):
            raise ValueError("candidate pointers are not strictly increasing")

        # Hypothesis: the pointer table is loaded into PS1 memory together
        # with the source file; its first target is at file offset 0x100.
        base_candidate = table[0] - PREFIX_BYTES
        if not (LOW_RAM <= base_candidate < HIGH_RAM and base_candidate % 4 == 0):
            raise ValueError("inferred RAM base outside expected KSEG0 range")
        offsets = [address - base_candidate for address in table]
        if any(offset < PREFIX_BYTES or offset + 4 > file_size for offset in offsets):
            raise ValueError("candidate pointer translates outside the file")
        target_tags = Counter()
        tag_0x41_indices = []
        for index, offset in enumerate(offsets):
            source.seek(offset)
            word_bytes = source.read(4)
            if len(word_bytes) != 4:
                raise ValueError("candidate target truncated")
            (tag,) = struct.unpack("<I", word_bytes)
            target_tags[tag] += 1
            if tag == 0x41:
                tag_0x41_indices.append(index)

        source.seek(0)
        source_sha256 = hashlib.sha256()
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            source_sha256.update(chunk)

    deltas = [b - a for a, b in zip(offsets, offsets[1:])]
    return {
        "schema": 1,
        "kind": "PRIVATE_CDFLR_POINTER_TABLE_PROBE",
        "source_name": path.name,
        "source_size_bytes": file_size,
        "source_sha256": source_sha256.hexdigest(),
        "header_bytes_examined": PREFIX_BYTES,
        "table_entries": count,
        "table_bytes": count * 4,
        "zero_padding_bytes": PREFIX_BYTES - count * 4,
        "base_address_candidate": f"0x{base_candidate:08X}",
        "first_target_file_offset": offsets[0],
        "last_target_file_offset": offsets[-1],
        "adjacent_target_span_count": len(deltas),
        "adjacent_target_span_min": min(deltas),
        "adjacent_target_span_max": max(deltas),
        "target_first_word_0x41_count": target_tags[0x41],
        "target_first_word_0x41_indices": tag_0x41_indices,
        "interpretation": {
            "status": "CANDIDATE_POINTER_TABLE_ONLY",
            "base_is_inferred_not_proven": True,
            "mapped_targets_not_decoded": True,
            "payload_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="local user-owned CDFLR.BIN")
    args = parser.parse_args()
    print(json.dumps(inspect_pointer_table(args.path), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
