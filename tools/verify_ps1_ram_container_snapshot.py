#!/usr/bin/env python3
"""Compare a PRIVATE PS1 RAM snapshot with a PRIVATE original container slice.

This utility never executes game code, uploads data, or exports source bytes.
It establishes exact byte equivalence (or a mismatch) at one chosen instant;
it does not independently prove which disc read loaded the RAM range.
"""
import argparse
import hashlib
import json
from pathlib import Path

RAM_BYTES = 2 * 1024 * 1024
DEFAULT_ADDRESS = 0x80183000
DEFAULT_BYTES = 0x3A000
DEFAULT_WINDOW_BYTES = 2048
MAX_WINDOWS = 32768


def _physical_ram_offset(address):
    if type(address) is not int:
        raise ValueError("RAM address must be an integer")
    if not (0x80000000 <= address < 0x80200000 or
            0xA0000000 <= address < 0xA0200000):
        raise ValueError("RAM address must refer to PS1 KSEG0/KSEG1 2MiB")
    return address & (RAM_BYTES - 1)


def compare_private_ram(container_path, ram_dump_path,
                        address=DEFAULT_ADDRESS,
                        compare_bytes=DEFAULT_BYTES,
                        container_offset=0,
                        window_bytes=DEFAULT_WINDOW_BYTES):
    if type(compare_bytes) is not int or compare_bytes <= 0:
        raise ValueError("compare_bytes must be a positive integer")
    if type(container_offset) is not int or container_offset < 0:
        raise ValueError("container_offset must be non-negative")
    if (type(window_bytes) is not int or window_bytes <= 0 or
            window_bytes > 64 * 1024):
        raise ValueError("window_bytes must be 1..65536")
    windows = (compare_bytes + window_bytes - 1) // window_bytes
    if windows > MAX_WINDOWS:
        raise ValueError("too many windows for bounded metadata report")

    physical_offset = _physical_ram_offset(address)
    container_path = Path(container_path)
    ram_dump_path = Path(ram_dump_path)
    if ram_dump_path.stat().st_size != RAM_BYTES:
        raise ValueError("RAM dump must be exactly 2,097,152 raw bytes")
    if physical_offset + compare_bytes > RAM_BYTES:
        raise ValueError("requested RAM slice crosses the 2MiB boundary")
    if container_offset + compare_bytes > container_path.stat().st_size:
        raise ValueError("requested source slice exceeds container bounds")

    container_sha = hashlib.sha256()
    ram_sha = hashlib.sha256()
    matching_windows = 0
    matching_prefix_bytes = 0
    different_bytes = 0
    first_mismatch = None
    matched_window_indices = []
    with container_path.open("rb") as container, ram_dump_path.open("rb") as ram:
        container.seek(container_offset)
        ram.seek(physical_offset)
        remaining = compare_bytes
        index = 0
        while remaining:
            size = min(remaining, window_bytes)
            source_chunk = container.read(size)
            memory_chunk = ram.read(size)
            if len(source_chunk) != size or len(memory_chunk) != size:
                raise ValueError("truncated container or RAM during comparison")
            container_sha.update(source_chunk)
            ram_sha.update(memory_chunk)
            if source_chunk == memory_chunk:
                matching_windows += 1
                matched_window_indices.append(index)
                if first_mismatch is None:
                    matching_prefix_bytes += size
            else:
                for j, (a, b) in enumerate(zip(source_chunk, memory_chunk)):
                    if a != b:
                        different_bytes += 1
                        if first_mismatch is None:
                            first_mismatch = index * window_bytes + j
                            matching_prefix_bytes += j
            index += 1
            remaining -= size

    exact = different_bytes == 0
    return {
        "schema": 1,
        "kind": "PRIVATE_PS1_RAM_CONTAINER_SNAPSHOT_COMPARISON",
        "container_name": container_path.name,
        "ram_dump_name": ram_dump_path.name,
        "ram_address": f"0x{address:08X}",
        "ram_physical_offset": physical_offset,
        "source_file_offset": container_offset,
        "compared_bytes": compare_bytes,
        "window_bytes": window_bytes,
        "window_count": windows,
        "matching_window_count": matching_windows,
        "matching_window_indices": matched_window_indices,
        "matching_prefix_bytes": matching_prefix_bytes,
        "different_byte_count": different_bytes,
        "first_difference_offset_in_slice": first_mismatch,
        "container_slice_sha256": container_sha.hexdigest(),
        "ram_slice_sha256": ram_sha.hexdigest(),
        "comparison_status": "EXACT_MATCH" if exact else "NOT_IDENTICAL_AT_SNAPSHOT",
        "interpretation": {
            "exact_match_proves_byte_equality_at_capture_time": exact,
            "exact_match_alone_does_not_prove_how_data_was_loaded": True,
            "mismatch_does_not_exclude_prior_load_and_mutation": True,
            "snapshot_timing_must_be_recorded_separately": True,
            "original_content_bytes_emitted": False,
        },
    }


def _int_auto(value):
    return int(value, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container", type=Path, help="private original CDFLR.BIN")
    parser.add_argument("ram_dump", type=Path, help="private raw 2MiB PS1 RAM dump")
    parser.add_argument("--address", type=_int_auto, default=DEFAULT_ADDRESS)
    parser.add_argument("--bytes", type=_int_auto, default=DEFAULT_BYTES)
    parser.add_argument("--container-offset", type=_int_auto, default=0)
    parser.add_argument("--window-bytes", type=_int_auto, default=DEFAULT_WINDOW_BYTES)
    args = parser.parse_args()
    print(json.dumps(compare_private_ram(
        args.container, args.ram_dump, address=args.address,
        compare_bytes=args.bytes, container_offset=args.container_offset,
        window_bytes=args.window_bytes,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
