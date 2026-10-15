#!/usr/bin/env python3
"""Summarize MIPS integer multiply/shift instructions in the original rotation builder.

Static evidence only: counts are not proof of coefficient data flow.
No original code bytes or lookup-table samples are emitted.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN


def classify(word):
    if word == 0:  # architectural NOP, not a meaningful SLL
        return None
    op = word >> 26
    rs, rt, rd, sa, fn = ((word >> 21) & 31, (word >> 16) & 31,
                         (word >> 11) & 31, (word >> 6) & 31, word & 63)
    if op == 0:
        if fn in (24, 25) and rd == 0 and sa == 0:
            return ('MULT' if fn == 24 else 'MULTU', (rs, rt))
        if fn in (16, 18) and rs == 0 and rt == 0 and sa == 0:
            return ('MFHI' if fn == 16 else 'MFLO', (rd,))
        if fn in (0, 2, 3) and rs == 0:
            return ({0: 'SLL', 2: 'SRL', 3: 'SRA'}[fn], (rd, rt, sa))
        if fn in (4, 6, 7) and sa == 0:
            return ({4: 'SLLV', 6: 'SRLV', 7: 'SRAV'}[fn], (rd, rt, rs))
    return None


def analyze(image, base, start=BUILDER, end=RETURN):
    if start < base or end < start or (start-base) % 4 or (end-base) % 4 or end+4 > base+len(image):
        return {'valid_range': False, 'instructions': [], 'counts': {}}
    instructions = []
    counts = {}
    for pc in range(start, end+4, 4):
        word = struct.unpack_from('<I', image, pc-base)[0]
        decoded = classify(word)
        if decoded is None:
            continue
        name, operands = decoded
        instructions.append({'pc': f'0x{pc:08X}', 'mnemonic': name,
                             'registers_or_shift': list(operands)})
        counts[name] = counts.get(name, 0) + 1
    return {'valid_range': True, 'builder': f'0x{start:08X}',
            'end_inclusive': f'0x{end:08X}',
            'instructions': instructions, 'counts': counts,
            'coefficient_dataflow_proven': False, 'assets_emitted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(analyze(image, base), indent=2))


if __name__ == '__main__':
    main()
