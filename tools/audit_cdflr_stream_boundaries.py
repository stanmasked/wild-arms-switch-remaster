#!/usr/bin/env python3
"""Profile candidate data streams inside PRIVATE CDFLR fixed-size slots.

No original bytes, images, palettes or decompressed content are emitted.
The optional toy flag-token grammar is a falsification probe, NOT a decoder.
"""
import argparse
import json
import struct
from pathlib import Path

SLOT_BYTES = 0x3A000
PTR_COUNT = 58
HEADER_BYTES = 256
STREAM_INDICES = tuple(range(43, 58, 2))
MAX_SLOTS = 1024
MAX_SLOT_BYTES = 4 * 1024 * 1024
MAX_TEST_OUTPUT = 2 * 1024 * 1024
CANDIDATE_MARKER = 0x8000


def probe_flag_tokens(source, expected_output=0x8000):
    """Exercise ONE simplified LSB-first flag/LZSS token-size hypothesis.

    Bit 1: one literal byte. Bit 0: two reference bytes, length
    (second_byte >> 4) + 3. Only stream positions are counted; reference
    semantics and produced bytes are NEVER reconstructed or validated.
    """
    if type(expected_output) is not int or not 1 <= expected_output <= MAX_TEST_OUTPUT:
        raise ValueError("output hypothesis outside bound")
    cursor = 4
    output = 0
    flags = 0
    remaining_flag_bits = 0
    n = len(source)
    if n < 4:
        return "TRUNCATED", 0, cursor
    while output < expected_output:
        if remaining_flag_bits == 0:
            if cursor >= n:
                return "TRUNCATED", output, cursor
            flags = source[cursor]
            cursor += 1
            remaining_flag_bits = 8
        if flags & 1:
            if cursor >= n:
                return "TRUNCATED", output, cursor
            cursor += 1
            output += 1
        else:
            if cursor + 2 > n:
                return "TRUNCATED", output, cursor
            output += (source[cursor + 1] >> 4) + 3
            cursor += 2
        remaining_flag_bits -= 1
        flags >>= 1
    if output > expected_output:
        return "OUTPUT_OVERSHOOT", output, cursor
    return ("NEAR_BOUNDARY" if 0 <= n - cursor <= 3 else "EARLY_OR_TRAILING_DATA",
            output, cursor)


def audit_streams(path, *, slot_bytes=SLOT_BYTES,
                  output_size_hypothesis=0x8000):
    if (type(slot_bytes) is not int or slot_bytes % 4 or
            not HEADER_BYTES + 4 <= slot_bytes <= MAX_SLOT_BYTES):
        raise ValueError("invalid fixed slot geometry")
    if (type(output_size_hypothesis) is not int or
            not 1 <= output_size_hypothesis <= MAX_TEST_OUTPUT):
        raise ValueError("output_size_hypothesis outside bound")
    path = Path(path)
    size = path.stat().st_size
    if size <= 0 or size % slot_bytes:
        raise ValueError("source size is not a whole number of slots")
    slots = size // slot_bytes
    if slots > MAX_SLOTS:
        raise ValueError("too many slots for bounded report")

    summary = {j: {"stream_index": j,
                   "is_last_unbounded_stream": j == 57,
                   "count": 0,
                   "marker_0x8000_count": 0,
                   "span_min": None, "span_max": None,
                   "candidate_flag_tokens_truncated": 0,
                   "candidate_flag_tokens_overshoot": 0,
                   "candidate_flag_tokens_early_or_trailing": 0,
                   "candidate_flag_tokens_near_boundary": 0,
                   "span_larger_than_output_hypothesis": 0}
               for j in STREAM_INDICES}
    abnormal_markers = []
    oversized_last = []
    with path.open("rb") as source:
        for slot in range(slots):
            data = source.read(slot_bytes)
            if len(data) != slot_bytes:
                raise ValueError("short source read")
            words = struct.unpack_from("<58I", data)
            base = words[0] - HEADER_BYTES
            if base % 4 or not (0x80000000 <= base < 0x80200000):
                raise ValueError(f"slot {slot}: invalid candidate RAM base")
            if any(w % 4 or not (0x80000000 <= w < 0x80200000)
                   for w in words):
                raise ValueError(f"slot {slot}: invalid 58-pointer table")
            offsets = [w - base for w in words]
            if (offsets[0] != HEADER_BYTES or offsets[-1] + 4 > slot_bytes or
                    any(b <= a for a, b in zip(offsets, offsets[1:]))):
                raise ValueError(f"slot {slot}: invalid pointer ordering or bounds")
            # Header bytes [232:256] are opaque, not required to be zero.
            for j in STREAM_INDICES:
                start = offsets[j]
                end = offsets[j + 1] if j < 57 else slot_bytes
                stream = data[start:end]
                length = len(stream)
                value = struct.unpack_from("<I", stream)[0]
                row = summary[j]
                row["count"] += 1
                row["span_min"] = length if row["span_min"] is None else min(length, row["span_min"])
                row["span_max"] = length if row["span_max"] is None else max(length, row["span_max"])
                if value == CANDIDATE_MARKER:
                    row["marker_0x8000_count"] += 1
                else:
                    abnormal_markers.append({"slot_index": slot, "stream_index": j})
                if length > output_size_hypothesis:
                    row["span_larger_than_output_hypothesis"] += 1
                    if j == 57:
                        oversized_last.append(slot)
                if j != 57:  # last span has no confirmed item end
                    status, _, _ = probe_flag_tokens(stream, output_size_hypothesis)
                    row[{
                        "TRUNCATED": "candidate_flag_tokens_truncated",
                        "OUTPUT_OVERSHOOT": "candidate_flag_tokens_overshoot",
                        "EARLY_OR_TRAILING_DATA": "candidate_flag_tokens_early_or_trailing",
                        "NEAR_BOUNDARY": "candidate_flag_tokens_near_boundary",
                    }[status]] += 1

    return {
        "schema": 1,
        "kind": "PRIVATE_CDFLR_STREAM_BOUNDARY_AUDIT",
        "source_name": path.name,
        "source_size_bytes": size,
        "slot_bytes": slot_bytes,
        "slot_count": slots,
        "candidate_streams_per_slot": len(STREAM_INDICES),
        "candidate_stream_count": slots * len(STREAM_INDICES),
        "candidate_0x8000_marker_match_count": sum(
            row["marker_0x8000_count"] for row in summary.values()),
        "candidate_marker_exception_sites": abnormal_markers,
        "bounded_by_next_pointer_stream_count": slots * (len(STREAM_INDICES) - 1),
        "last_stream_upper_bound_larger_than_output_hypothesis_slots": oversized_last,
        "candidate_token_grammar": {
            "flags": "LSB-first; 1=one literal, 0=two-byte reference",
            "reference_output_count": "high nibble of second ref byte + 3",
            "proposed_output_byte_count": output_size_hypothesis,
            "does_not_validate_back_references_or_produce_pixels": True,
        },
        "stream_profiles": [summary[j] for j in STREAM_INDICES],
        "interpretation": {
            "0x8000_value_is_observed_not_verified_decompressed_size": True,
            "toy_token_grammar_not_a_decoder": True,
            "reaching_0x8000_output_without_matching_input_boundary_is_not_validation": True,
            "last_stream_length_only_upper_bounded_by_slot": True,
            "original_payload_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource", type=Path, help="private original CDFLR.BIN")
    parser.add_argument("--slot-bytes", type=lambda x: int(x, 0), default=SLOT_BYTES)
    parser.add_argument("--output-size-hypothesis", type=lambda x: int(x, 0),
                        default=0x8000)
    args = parser.parse_args()
    print(json.dumps(audit_streams(args.resource, slot_bytes=args.slot_bytes,
                                  output_size_hypothesis=args.output_size_hypothesis),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
