#!/usr/bin/env python3
"""Metadata-only MIPS pattern checks on a local user-owned PS-X EXE.

Looks for one specific argument setup and one bounded 16-byte memory-copy
loop involving the CDFLR base-address candidate. It does not execute MIPS,
decode proprietary data, or prove which disc file is loaded.
"""
import argparse
import json
import struct
from pathlib import Path

PSX_HEADER_BYTES = 0x800
MAX_EXE_BYTES = 8 * 1024 * 1024
TARGET_BASE = 0x80183000


def _op(w):
    return w >> 26


def _rs(w):
    return (w >> 21) & 31


def _rt(w):
    return (w >> 16) & 31


def _imm(w):
    return w & 0xFFFF


def _lui(w, reg, value):
    return _op(w) == 15 and _rs(w) == 0 and _rt(w) == reg and _imm(w) == value


def _ori(w, dest, src, value):
    return _op(w) == 13 and _rs(w) == src and _rt(w) == dest and _imm(w) == value


def _lw(w, dest, base, off):
    return _op(w) == 35 and _rs(w) == base and _rt(w) == dest and _imm(w) == off


def _sw(w, src, base, off):
    return _op(w) == 43 and _rs(w) == base and _rt(w) == src and _imm(w) == off


def _addiu(w, dest, src, value):
    return _op(w) == 9 and _rs(w) == src and _rt(w) == dest and _imm(w) == value


def _bne(w, lhs, rhs, signed_rel):
    return (_op(w) == 5 and _rs(w) == lhs and _rt(w) == rhs
            and _imm(w) == signed_rel & 0xFFFF)


def _load_argument_sequence(words):
    if len(words) < 7:
        return False
    return (
        _lui(words[0], 5, 0x8018) and _ori(words[1], 5, 5, 0x3000) and
        _lui(words[2], 6, 0x0003) and
        _lui(words[3], 4, 0x800D) and _lw(words[4], 4, 4, 0x2EA0) and
        _op(words[5]) == 3 and  # JAL, argument a2 completed in delay slot
        _ori(words[6], 6, 6, 0xA000)
    )


def _copy_loop_sequence(words):
    if len(words) < 16:
        return False
    if not (
        _lui(words[0], 7, 0x8018) and _ori(words[1], 7, 7, 0x3000) and
        _lui(words[2], 6, 0x8020) and
        _lui(words[3], 8, 0x8023) and _ori(words[4], 8, 8, 0xA000)
    ):
        return False
    for i, offset in enumerate((0, 4, 8, 12)):
        if not _lw(words[5 + i], 2 + i, 6, offset):
            return False
        if not _sw(words[9 + i], 2 + i, 7, offset):
            return False
    return (
        _addiu(words[13], 6, 6, 16) and
        _bne(words[14], 6, 8, -10) and
        _addiu(words[15], 7, 7, 16)
    )


def audit_loader(path):
    path = Path(path)
    file_size = path.stat().st_size
    if file_size < PSX_HEADER_BYTES or file_size > MAX_EXE_BYTES:
        raise ValueError("PS-X EXE outside bounded file size")
    raw = path.read_bytes()
    if raw[:8] != b"PS-X EXE":
        raise ValueError("not a PS-X EXE")
    text_base = struct.unpack_from("<I", raw, 0x18)[0]
    text_bytes = struct.unpack_from("<I", raw, 0x1C)[0]
    if (text_bytes < 64 or text_bytes % 4 or
            PSX_HEADER_BYTES + text_bytes > file_size):
        raise ValueError("invalid bounded PS-X EXE text extent")
    instructions = struct.unpack_from("<" + str(text_bytes // 4) + "I",
                                       raw, PSX_HEADER_BYTES)
    load_calls = []
    copy_loops = []
    base_constructors = []
    for i in range(len(instructions) - 1):
        a, b = instructions[i:i + 2]
        if (_op(a) == 15 and _rs(a) == 0 and _imm(a) == 0x8018 and
                _ori(b, _rt(a), _rt(a), 0x3000)):
            base_constructors.append(PSX_HEADER_BYTES + i * 4)
        if _load_argument_sequence(instructions[i:i + 7]):
            off = PSX_HEADER_BYTES + i * 4
            jal = instructions[i + 5]
            jal_pc = text_base + (off - PSX_HEADER_BYTES) + 20
            call_addr = ((jal_pc + 4) & 0xF0000000) | ((jal & 0x03FFFFFF) << 2)
            load_calls.append({
                "file_offset": off,
                "buffer_address_candidate": f"0x{TARGET_BASE:08X}",
                "size_argument_bytes": 0x3A000,
                "call_target_address": f"0x{call_addr:08X}",
            })
        if _copy_loop_sequence(instructions[i:i + 16]):
            off = PSX_HEADER_BYTES + i * 4
            copy_loops.append({
                "file_offset": off,
                "source_address": "0x80200000",
                "destination_address": f"0x{TARGET_BASE:08X}",
                "end_source_address": "0x8023A000",
                "copy_bytes": 0x3A000,
                "stride_bytes": 16,
                "loop_iterations": 0x3A000 // 16,
            })
    return {
        "schema": 1,
        "kind": "PSX_MAIN_EXE_CDFLR_BASE_CODE_CORROBORATION",
        "source_name": path.name,
        "source_size_bytes": file_size,
        "declared_text_bytes": text_bytes,
        "candidate_ram_base": f"0x{TARGET_BASE:08X}",
        "base_lui_ori_constructor_offsets": base_constructors,
        "loader_argument_call_sites": load_calls,
        "memory_copy_loops": copy_loops,
        "interpretation": {
            "code_patterns_structurally_verified": True,
            "relationship_to_named_cdflr_file_not_proven": True,
            "untrusted_game_code_never_executed": True,
            "proprietary_code_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="private local WILDARMS.EXE")
    args = parser.parse_args()
    print(json.dumps(audit_loader(args.executable), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
