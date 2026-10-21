#!/usr/bin/env python3
"""Bounded, metadata-only probe for unknown local PS1 container candidates.

The tool never prints or exports source bytes. It hashes the complete input in
streaming mode, but reads at most --sample-bytes from the beginning for
entropy/zero-ratio and aligned little-endian pointer-like word statistics.
Those words are hypotheses, not proof of a container format.
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


def _entropy(counts, total):
    if total <= 0:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts if n)


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
        source.seek(0)
        sample = source.read(min(size, sample_bytes))

    counts = Counter(sample)
    pointer_counts = Counter()
    aligned_words = len(sample) // 4
    for offset in range(0, aligned_words * 4, 4):
        value = int.from_bytes(sample[offset:offset + 4], "little")
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
            "offset": 0,
            "bytes_read": len(sample),
            "limit_bytes": sample_bytes,
            "shannon_entropy_bits_per_byte": round(_entropy(counts.values(), len(sample)), 6),
            "zero_byte_fraction": round(counts.get(0, 0) / len(sample), 6),
            "aligned_u32_words_examined": aligned_words,
        },
        "pointer_like_words": [
            {"value": value, "count": count}
            for value, count in pointer_counts.most_common(TOP_POINTERS)
            if count >= 2
        ],
        "interpretation": {
            "status": "HEURISTIC_ONLY",
            "pointer_like_words_are_not_proven_offsets": True,
            "payload_bytes_emitted": False,
            "complete_file_loaded_into_memory": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="path to a local, user-owned container file")
    parser.add_argument("--sample-bytes", type=int, default=DEFAULT_SAMPLE_BYTES,
                        help=f"maximum prefix read for statistics (1..{MAX_SAMPLE_BYTES})")
    args = parser.parse_args()
    print(json.dumps(probe(args.path, args.sample_bytes), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
