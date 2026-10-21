#!/usr/bin/env python3
"""Bounded, metadata-only probe for unknown local PS1 container candidates.

The tool never prints or exports source bytes. It hashes the complete input in
streaming mode and samples at most --sample-bytes across up to eight evenly
spaced windows. Statistics and pointer-like words are hypotheses, not proof
of a container format.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

DEFAULT_SAMPLE_BYTES = 1024 * 1024
MAX_SAMPLE_BYTES = 8 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
POINTER_MIN = 0x20
TOP_POINTERS = 16
SAMPLE_WINDOWS = 8


def _entropy(counts, total):
    if total <= 0:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts if n)


def _window_offsets(size, sample_bytes):
    """Return aligned, non-overlapping sample windows within the byte budget."""
    if size <= sample_bytes:
        return [(0, size)]
    window_count = min(SAMPLE_WINDOWS, max(1, sample_bytes // 4))
    window_size = sample_bytes // window_count
    if window_size <= 0:
        return [(0, min(size, sample_bytes))]
    if window_count == 1:
        return [(0, window_size)]
    offsets = []
    for index in range(window_count):
        raw_offset = (size - window_size) * index // (window_count - 1)
        offset = raw_offset - (raw_offset % 4)
        if offsets and offset < offsets[-1] + window_size:
            offset = offsets[-1] + window_size
            offset -= offset % 4
        if offset + window_size <= size and (not offsets or offset > offsets[-1]):
            offsets.append(offset)
    if not offsets:
        offsets = [0]
    return [(offset, min(window_size, size - offset)) for offset in offsets]


def probe(path, sample_bytes=DEFAULT_SAMPLE_BYTES):
    if type(sample_bytes) is not int or sample_bytes < 1 or sample_bytes > MAX_SAMPLE_BYTES:
        raise ValueError(f"sample_bytes must be between 1 and {MAX_SAMPLE_BYTES}")
    path = Path(path)
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("container candidate is empty")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)

        offsets = _window_offsets(size, sample_bytes)
        counts = Counter()
        pointer_counts = Counter()
        sample_total = 0
        aligned_words = 0
        for offset, length in offsets:
            source.seek(offset)
            sample = source.read(length)
            if len(sample) != length:
                raise ValueError("candidate changed or truncated while sampling")
            counts.update(sample)
            sample_total += len(sample)
            words = len(sample) // 4
            aligned_words += words
            for word_index in range(words):
                word_offset = word_index * 4
                value = int.from_bytes(sample[word_offset:word_offset + 4], "little")
                # A pointer-like value must be in-file and leave room for a small header.
                if POINTER_MIN <= value < size:
                    pointer_counts[value] += 1

    return {
        "schema": 1,
        "kind": "BOUNDED_LOCAL_CONTAINER_PROBE",
        "input_name": path.name,
        "file_size_bytes": size,
        "sha256": digest.hexdigest(),
        "sample": {
            "bytes_read": sample_total,
            "limit_bytes": sample_bytes,
            "windows": [{"offset": offset, "bytes_read": length} for offset, length in offsets],
            "shannon_entropy_bits_per_byte": round(_entropy(counts.values(), sample_total), 6),
            "zero_byte_fraction": round(counts.get(0, 0) / sample_total, 6),
            "aligned_u32_words_examined": aligned_words,
        },
        "pointer_like_words": [
            {"value": value, "count": count}
            for value, count in pointer_counts.most_common(TOP_POINTERS)
            if count >= 2
        ],
        "interpretation": {
            "status": "HEURISTIC_ONLY",
            "sample_windows_are_not_a_complete_format_scan": True,
            "pointer_like_words_are_not_proven_offsets": True,
            "payload_bytes_emitted": False,
            "complete_file_loaded_into_memory": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="path to a local, user-owned container file")
    parser.add_argument("--sample-bytes", type=int, default=DEFAULT_SAMPLE_BYTES,
                        help=f"total sample budget (1..{MAX_SAMPLE_BYTES})")
    args = parser.parse_args()
    print(json.dumps(probe(args.path, args.sample_bytes), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
