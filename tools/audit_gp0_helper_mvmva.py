#!/usr/bin/env python3
"""Audit the original helper's GTE MVMVA -> IR1/IR2/IR3 -> a1 stores.

Static specific-address evidence only; never exports original EXE bytes.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

HELPER = 0x800B68E8


def instruction(word):
    op, rs, rt, rd = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    imm = word & 65535
    if op == 35:
        return ('LW', rt, rs, imm - 65536 if imm >= 32768 else imm)
    if op == 18 and rs == 4:
        return ('MTC2', rt, rd)
    if op == 18 and rs & 16:
        return ('GTE', word & 63)
    if op == 58:
        return ('SWC2', rt, rs, imm - 65536 if imm >= 32768 else imm)
    return None


def scan(image, base, entry=HELPER):
    if entry < base or entry + 40 > base + len(image) or (entry - base) % 4:
        return {'helper': f'0x{entry:08X}', 'matched': False, 'reason': 'entry outside load image'}
    ins = [instruction(struct.unpack_from('<I', image, entry-base+4*i)[0]) for i in range(10)]
    # Allow a single NOP between COP2 register moves and MVMVA, but keep
    # strict word offsets: this is evidence for one specific original routine.
    expected = [('LW', 8, 4, 0), ('LW', 9, 4, 4),
                ('MTC2', 8, 0), ('MTC2', 9, 1), None,
                ('GTE', 0x12), ('SWC2', 9, 5, 0),
                ('SWC2', 10, 5, 4), ('SWC2', 11, 5, 8)]
    valid = all(ins[i] == exp for i, exp in enumerate(expected) if exp is not None)
    nop = struct.unpack_from('<I', image, entry-base+16)[0] == 0
    return {'helper': f'0x{entry:08X}', 'matched': valid and nop,
            'input': 'LW a0+0/+4 -> MTC2 VXY0/VZ0',
            'gte_command': 'MVMVA (opcode 0x12)' if valid else None,
            'result_registers': ['IR1', 'IR2', 'IR3'] if valid else [],
            'a1_word_offsets': [0, 4, 8] if valid else [],
            'gp0_opcode_or_uv_recovered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(scan(image, base), indent=2))


if __name__ == '__main__':
    main()
