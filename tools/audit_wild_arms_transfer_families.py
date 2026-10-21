#!/usr/bin/env python3
"""Bounded metadata-only audit of shared PS-X EXE transfer call families.

Recognizes adjacent LUI/LW constant-base reads near a JAL. This is NOT
whole-program dataflow analysis or proof of a particular disc-file origin.
"""
import argparse
import json
import struct
from collections import Counter
from pathlib import Path

HEADER_BYTES = 0x800
MAX_EXE_BYTES = 8 * 1024 * 1024
CALLEE = 0x8002356C
SOURCE_SLOT = 0x800D2EA0
SOURCE_HIGH = 0x800D
WINDOW_WORDS = 8
STORE_OPCODES = frozenset((40, 41, 42, 43, 46))


def _op(word):
    return word >> 26


def _rs(word):
    return (word >> 21) & 31


def _rt(word):
    return (word >> 16) & 31


def _imm(word):
    return word & 0xFFFF


def _is_lui(word, reg, high):
    return _op(word) == 15 and _rs(word) == 0 and _rt(word) == reg and _imm(word) == high


def _jal_target(word, pc):
    if _op(word) != 3:
        return None
    return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def inspect_call_families(path, target=CALLEE):
    path = Path(path)
    size = path.stat().st_size
    if not HEADER_BYTES + 4 <= size <= MAX_EXE_BYTES:
        raise ValueError("PS-X EXE outside bounded size")
    raw = path.read_bytes()
    if raw[:8] != b"PS-X EXE":
        raise ValueError("invalid PS-X EXE magic")
    base, text_size = struct.unpack_from("<II", raw, 0x18)
    if not text_size or text_size % 4 or HEADER_BYTES + text_size > len(raw):
        raise ValueError("invalid declared text extent")
    end = base + text_size
    if not 0x80000000 <= base < end <= 0x80200000:
        raise ValueError("declared text outside PS1 KSEG0 2MiB")
    if not base <= target < end:
        raise ValueError("target outside declared executable text")
    words = struct.unpack_from("<" + str(text_size // 4) + "I", raw, HEADER_BYTES)
    literal = struct.pack("<I", SOURCE_SLOT)
    literal_offsets = [HEADER_BYTES + index * 4 for index, w in enumerate(words)
                       if struct.pack("<I", w) == literal]

    slot_read_sites = []
    slot_write_sites = []
    all_low_imm_store_sites = []
    for i, w in enumerate(words):
        if _op(w) in STORE_OPCODES and _imm(w) == SOURCE_SLOT & 0xFFFF:
            all_low_imm_store_sites.append(HEADER_BYTES + i * 4)
        if i == 0 or _imm(w) != SOURCE_SLOT & 0xFFFF:
            continue
        if not _is_lui(words[i - 1], _rs(w), SOURCE_HIGH):
            continue
        if _op(w) == 35:
            slot_read_sites.append(HEADER_BYTES + i * 4)
        elif _op(w) in STORE_OPCODES:
            slot_write_sites.append(HEADER_BYTES + i * 4)

    call_sites = []
    families = Counter()
    for i, word in enumerate(words):
        if _jal_target(word, base + i * 4) != target:
            continue
        candidate_reads = []
        for j in range(max(1, i - WINDOW_WORDS), i):
            w = words[j]
            if _op(w) != 35 or not _is_lui(words[j - 1], _rs(w), SOURCE_HIGH):
                continue
            if not 0x2E00 <= _imm(w) < 0x2F00:
                continue
            candidate_reads.append({
                "file_offset": HEADER_BYTES + j * 4,
                "slot": f"0x{(SOURCE_HIGH << 16) + _imm(w):08X}",
                "destination_register_number": _rt(w),
            })
        slots = sorted(set(item["slot"] for item in candidate_reads))
        for slot in slots:
            families[slot] += 1
        call_sites.append({
            "file_offset": HEADER_BYTES + i * 4,
            "nearby_direct_global_loads": candidate_reads,
            "candidate_global_slots": slots,
        })

    callee_start = (target - base) // 4
    region_stop = min(callee_start + 0x140 // 4, len(words))
    argument_halfword_reads = [
        HEADER_BYTES + i * 4 for i in range(callee_start, region_stop)
        if _op(words[i]) == 37 and _rs(words[i]) == 4 and
        _rt(words[i]) == 2 and _imm(words[i]) == 0
    ]
    return {
        "schema": 1,
        "kind": "WILD_ARMS_TRANSFER_CALL_FAMILY_STATIC_AUDIT",
        "source_name": path.name,
        "declared_text_end": f"0x{end:08X}",
        "target_function": f"0x{target:08X}",
        "call_site_count": len(call_sites),
        "call_sites": call_sites,
        "nearby_slot_call_families": [
            {"slot": slot, "call_site_count": count}
            for slot, count in sorted(families.items())
        ],
        "calls_without_candidate_nearby_slot": sum(
            not site["candidate_global_slots"] for site in call_sites
        ),
        "direct_adjacent_lui_lw_source_slot_reads": slot_read_sites,
        "direct_adjacent_lui_store_source_slot_writes": slot_write_sites,
        "all_store_immediate_0x2ea0_sites": all_low_imm_store_sites,
        "absolute_source_slot_literal_offsets": literal_offsets,
        "callee_a0_halfword_read_sites": argument_halfword_reads,
        "interpretation": {
            "adjacent_loads_not_full_argument_provenance": True,
            "no_direct_store_does_not_prove_no_writer": True,
            "callee_path_reachability_not_proven": True,
            "source_file_identity_not_proven": True,
            "no_original_bytes_emitted": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_call_families(args.executable), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
