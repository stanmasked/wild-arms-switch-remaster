#!/usr/bin/env python3
"""Metadata-only static provenance audit of Wild Arms PS-X EXE transfer calls.

No emulation and no protected opcode, text, sprite, or sound bytes are emitted.
This tool proves caller instruction shape, not which disc file was loaded.
"""
import argparse
import json
import struct
from pathlib import Path

MAX_EXE_BYTES = 8 * 1024 * 1024
PSX_HEADER_BYTES = 0x800
TARGET_FUNCTION = 0x8002356C
SOURCE_POINTER_SLOT = 0x800D2EA0
TARGET_BUFFER = 0x80183000
TRANSFER_BYTES = 0x3A000


def _op(word):
    return word >> 26


def _rs(word):
    return (word >> 21) & 31


def _rt(word):
    return (word >> 16) & 31


def _imm(word):
    return word & 0xffff


def _lui(word, dest, high):
    return _op(word) == 15 and _rs(word) == 0 and _rt(word) == dest and _imm(word) == high


def _ori(word, dest, source, immediate):
    return (_op(word) == 13 and _rt(word) == dest and
            _rs(word) == source and _imm(word) == immediate)


def _lw(word, dest, base, immediate):
    return (_op(word) == 35 and _rt(word) == dest and
            _rs(word) == base and _imm(word) == immediate)


def _jal_target(word, pc):
    if _op(word) != 3:
        return None
    return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def audit_transfer_calls(path, function_address=TARGET_FUNCTION):
    path = Path(path)
    size = path.stat().st_size
    if size < PSX_HEADER_BYTES + 4 or size > MAX_EXE_BYTES:
        raise ValueError("PS-X EXE file outside bounded size")
    data = path.read_bytes()
    if data[:8] != b"PS-X EXE":
        raise ValueError("invalid PS-X EXE magic")
    load_address, text_bytes = struct.unpack_from("<II", data, 0x18)
    if (text_bytes <= 0 or text_bytes % 4 or
            PSX_HEADER_BYTES + text_bytes > size):
        raise ValueError("invalid declared text range")
    if not (0x80000000 <= load_address < 0x80200000 and
            load_address + text_bytes <= 0x80200000):
        raise ValueError("declared text outside PS1 KSEG0 2 MiB")
    words = struct.unpack_from("<" + str(text_bytes // 4) + "I", data, PSX_HEADER_BYTES)

    calls = []
    relevant = []
    slot_reads = []
    for i, word in enumerate(words):
        off = PSX_HEADER_BYTES + i * 4
        pc = load_address + i * 4
        if _jal_target(word, pc) == function_address:
            calls.append(off)
            # Seven-word window around the source-pointer call, including
            # the MIPS JAL delay slot. No source bytes are exposed.
            if i >= 5 and i + 1 < len(words):
                window = words[i - 5:i + 2]
                match = (
                    _lui(window[0], 5, 0x8018) and
                    _ori(window[1], 5, 5, 0x3000) and
                    _lui(window[2], 6, 0x0003) and
                    _lui(window[3], 4, 0x800D) and
                    _lw(window[4], 4, 4, 0x2EA0) and
                    _ori(window[6], 6, 6, 0xA000)
                )
                if match:
                    relevant.append(off)
        # Limited to directly adjacent LUI/LW pairs; indirect writes and
        # full reaching-definition analysis are deliberately out of scope.
        if i + 1 < len(words):
            if (_lui(word, _rt(word), 0x800D) and
                    _lw(words[i + 1], _rt(words[i + 1]), _rt(word), 0x2EA0)):
                slot_reads.append(PSX_HEADER_BYTES + (i + 1) * 4)

    end = load_address + text_bytes
    source_slot_outside = SOURCE_POINTER_SLOT >= end or SOURCE_POINTER_SLOT < load_address
    return {
        "schema": 1,
        "kind": "WILD_ARMS_TRANSFER_CALL_STATIC_PROVENANCE",
        "exe_name": path.name,
        "exe_size_bytes": size,
        "load_address": f"0x{load_address:08X}",
        "declared_text_bytes": text_bytes,
        "declared_text_end_exclusive": f"0x{end:08X}",
        "called_function": f"0x{function_address:08X}",
        "function_inside_declared_text": load_address <= function_address < end,
        "call_site_count": len(calls),
        "call_file_offsets": calls,
        "matching_candidate_buffer_call_count": len(relevant),
        "matching_candidate_buffer_call_offsets": relevant,
        "candidate_buffer": f"0x{TARGET_BUFFER:08X}",
        "candidate_transfer_bytes": TRANSFER_BYTES,
        "candidate_source_pointer_slot": f"0x{SOURCE_POINTER_SLOT:08X}",
        "source_pointer_slot_outside_declared_text": source_slot_outside,
        "source_pointer_slot_distance_after_text": SOURCE_POINTER_SLOT - end if SOURCE_POINTER_SLOT >= end else None,
        "direct_lui_lw_source_slot_read_count": len(slot_reads),
        "direct_lui_lw_source_slot_read_offsets": slot_reads,
        "interpretation": {
            "callee_is_shared_between_call_sites": len(calls) > 1,
            "file_selection_and_buffer_provenance_not_proven": True,
            "static_reference_scan_is_not_full_dataflow": True,
            "outside_declared_text_does_not_prove_bss": True,
            "game_code_executed": False,
            "proprietary_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="private original WILDARMS.EXE")
    args = parser.parse_args()
    print(json.dumps(audit_transfer_calls(args.executable), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
