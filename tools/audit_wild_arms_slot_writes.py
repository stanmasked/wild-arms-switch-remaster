#!/usr/bin/env python3
"""Conservative straight-line MIPS constant-base store audit (metadata only).

Does not execute game code or infer runtime file selection. Constant propagation
is local to unbranched runs, with delay slots omitted from proofs. Undefined
registers, unknown opcodes, and control flow cannot certify target addresses.
"""
import argparse
import json
import struct
from pathlib import Path

TARGET = 0x800D2EA0
MAX_EXE_BYTES = 8 * 1024 * 1024
PSX_HEADER = 0x800
STORE_OPS = {40: "SB", 41: "SH", 42: "SWL", 43: "SW", 46: "SWR"}
LOAD_OPS = set((32, 33, 34, 35, 36, 37, 38))
BRANCH_OPS = set((1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23))


def sign16(value):
    return value - 0x10000 if value & 0x8000 else value


def audit_slot_writes(path, target=TARGET):
    path = Path(path)
    length = path.stat().st_size
    if not PSX_HEADER + 4 <= length <= MAX_EXE_BYTES:
        raise ValueError("PS-X EXE outside bounded file size")
    data = path.read_bytes()
    if data[:8] != b"PS-X EXE":
        raise ValueError("PS-X EXE magic mismatch")
    load_address, text_bytes = struct.unpack_from("<II", data, 0x18)
    if text_bytes <= 0 or text_bytes % 4 or PSX_HEADER + text_bytes > length:
        raise ValueError("invalid PS-X EXE declared text size")
    if not 0x80000000 <= load_address < load_address + text_bytes <= 0x80200000:
        raise ValueError("PS-X EXE text outside KSEG0 2MiB")
    if target < 0 or target > 0xFFFFFFFF:
        raise ValueError("target outside u32 address range")

    words = struct.unpack_from("<" + str(text_bytes // 4) + "I", data, PSX_HEADER)
    known = {0: 0}
    skip_delay_slot = False
    hits = []
    unexplained_low_immediate_stores = []
    reset_count = 0
    for i, word in enumerate(words):
        if skip_delay_slot:
            known = {0: 0}
            skip_delay_slot = False
            reset_count += 1
            continue
        op = word >> 26
        rs = (word >> 21) & 31
        rt = (word >> 16) & 31
        rd = (word >> 11) & 31
        immediate = word & 0xFFFF
        signed = sign16(immediate)
        offset = PSX_HEADER + 4 * i
        if op in STORE_OPS:
            if rs in known:
                address = (known[rs] + signed) & 0xFFFFFFFF
                if address == target:
                    hits.append({
                        "file_offset": offset,
                        "operation": STORE_OPS[op],
                        "base_register": rs,
                        "signed_displacement": signed,
                    })
            elif immediate == (target & 0xFFFF):
                unexplained_low_immediate_stores.append(offset)

        if op == 15:  # LUI
            if rs == 0 and rt != 0:
                known[rt] = immediate << 16
            else:
                known.pop(rt, None)
        elif op == 13:  # ORI
            if rt:
                known[rt] = ((known[rs] | immediate) & 0xFFFFFFFF) if rs in known else None
        elif op == 9:  # ADDIU
            if rt:
                known[rt] = ((known[rs] + signed) & 0xFFFFFFFF) if rs in known else None
        elif op == 12:  # ANDI
            if rt:
                known[rt] = (known[rs] & immediate) if rs in known else None
        elif op == 0:  # Register-register ALU, jump or unknown
            fn = word & 63
            shamt = (word >> 6) & 31
            if fn in (32, 33):  # ADD/ADDU
                known[rd] = ((known[rs] + known[rt]) & 0xFFFFFFFF) if rs in known and rt in known else None
            elif fn == 37:  # OR
                known[rd] = (known[rs] | known[rt]) if rs in known and rt in known else None
            elif fn == 0:  # SLL/NOP
                known[rd] = ((known[rt] << shamt) & 0xFFFFFFFF) if rt in known else None
            elif fn in (8, 9):  # JR/JALR
                skip_delay_slot = True
                known = {0: 0}
            else:
                known.pop(rd, None)
        elif op in LOAD_OPS:
            known.pop(rt, None)
        elif op in BRANCH_OPS:
            known = {0: 0}
            skip_delay_slot = True
        elif op in STORE_OPS:
            pass
        else:
            # Unknown I-type operation: invalidate its conventional rt.
            known.pop(rt, None)
        known = {reg: value for reg, value in known.items()
                 if reg == 0 or value is not None}
        known[0] = 0

    return {
        "schema": 1,
        "kind": "WILD_ARMS_STRAIGHT_LINE_STORE_AUDIT",
        "source_name": path.name,
        "declared_text_bytes": text_bytes,
        "target_address": f"0x{target:08X}",
        "computed_constant_target_store_count": len(hits),
        "computed_constant_target_store_sites": hits,
        "unknown_base_same_low_immediate_sites": unexplained_low_immediate_stores,
        "flow_resets_after_control_transfer": reset_count,
        "interpretation": {
            "only_constant_register_values_within_linear_runs": True,
            "control_transfer_delay_slots_not_audited": True,
            "unknown_loads_and_indirect_writers_not_resolved": True,
            "absence_of_proven_stores_not_absence_of_runtime_writes": True,
            "file_selection_not_inferred": True,
            "original_bytes_emitted": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_slot_writes(args.executable), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
