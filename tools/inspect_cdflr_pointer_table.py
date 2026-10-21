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


def corroborate_base_in_psx_exe(executable_path, base_candidate):
    """Bounded literal-match check against a native PS-X EXE.

    This does NOT prove the executable loads this container at the address.
    """
    executable_path = Path(executable_path)
    size = executable_path.stat().st_size
    if size < 0x800 or size > 8 * 1024 * 1024:
        raise ValueError("PS-X EXE outside bounded inspection size")
    exe = executable_path.read_bytes()
    if exe[:8] != b"PS-X EXE":
        raise ValueError("not a PS-X EXE header")
    (text_bytes,) = struct.unpack_from("<I", exe, 0x1C)
    if text_bytes <= 0 or 0x800 + text_bytes > len(exe):
        raise ValueError("invalid PS-X EXE text bounds")
    needle = struct.pack("<I", base_candidate)
    offsets = [i for i in range(0x800, 0x800 + text_bytes, 4)
               if exe[i:i + 4] == needle]
    return {
        "source_name": executable_path.name,
        "psx_exe_header_verified": True,
        "aligned_literal_match_count": len(offsets),
        "aligned_literal_file_offsets": offsets,
        "loader_relationship_not_proven": True,
    }


def inspect_pointer_table(path, executable_path=None):
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
        type_0x41_span_rules = []
        for index, offset in enumerate(offsets):
            source.seek(offset)
            word_bytes = source.read(4)
            if len(word_bytes) != 4:
                raise ValueError("candidate target truncated")
            (tag,) = struct.unpack("<I", word_bytes)
            target_tags[tag] += 1
            if tag == 0x41:
                tag_0x41_indices.append(index)
                if index + 1 < len(offsets) and offset + 20 <= offsets[index + 1]:
                    source.seek(offset)
                    head = source.read(20)
                    if len(head) != 20:
                        raise ValueError("candidate type 0x41 header truncated")
                    kind, zero, one, length_field, count_field = struct.unpack("<5I", head)
                    actual_span = offsets[index + 1] - offset
                    header_pattern = kind == 0x41 and zero == 0 and one == 1
                    size_rule = actual_span == length_field + 8 * count_field + 12
                    type_0x41_span_rules.append({
                        "index": index,
                        "header_pattern": header_pattern,
                        "size_rule": size_rule,
                        "length_field": length_field,
                        "count_field": count_field,
                    })

        source.seek(0)
        source_sha256 = hashlib.sha256()
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            source_sha256.update(chunk)

    deltas = [b - a for a, b in zip(offsets, offsets[1:])]
    corroboration = (corroborate_base_in_psx_exe(executable_path, base_candidate)
                     if executable_path is not None else None)
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
        "type_0x41_span_rule_candidate_count": len(type_0x41_span_rules),
        "type_0x41_header_pattern_matches": sum(r["header_pattern"] for r in type_0x41_span_rules),
        "type_0x41_span_rule_matches": sum(r["size_rule"] for r in type_0x41_span_rules),
        "type_0x41_span_rule_fail_indices": [r["index"] for r in type_0x41_span_rules if not r["size_rule"]],
        "type_0x41_length_field_min": min((r["length_field"] for r in type_0x41_span_rules), default=None),
        "type_0x41_length_field_max": max((r["length_field"] for r in type_0x41_span_rules), default=None),
        "type_0x41_count_field_min": min((r["count_field"] for r in type_0x41_span_rules), default=None),
        "type_0x41_count_field_max": max((r["count_field"] for r in type_0x41_span_rules), default=None),
        "independent_executable_literal_check": corroboration,
        "interpretation": {
            "status": "CANDIDATE_POINTER_TABLE_ONLY",
            "base_is_inferred_not_proven": True,
            "mapped_targets_not_decoded": True,
            "type_0x41_field_meanings_not_proven": True,
            "payload_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="local user-owned CDFLR.BIN")
    parser.add_argument("--executable", type=Path, help="optional local PS-X EXE for independent literal check")
    args = parser.parse_args()
    print(json.dumps(inspect_pointer_table(args.path, args.executable), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
