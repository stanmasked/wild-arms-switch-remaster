#!/usr/bin/env python3
"""Decode original MVMVA control bits without executing emulated game code."""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

HELPER_COMMAND_PC = 0x800B68FC
EXPECTED_COMMAND_WORD = 0x4A486012
MATRIX = ('rotation', 'light', 'color', 'reserved')
VECTOR = ('V0', 'V1', 'V2', 'IR')
TRANSLATION = ('TR', 'BK', 'FC', 'none')


def decode_mvmva(word):
    # COP2 command requires the COP2 opcode, execution/CO bit and function 0x12.
    if word >> 26 != 0x12 or not (word & (1 << 25)) or (word & 0x3f) != 0x12:
        return None
    mx, vx, cv = (word >> 17) & 3, (word >> 15) & 3, (word >> 13) & 3
    return {'opcode': 'MVMVA', 'command_word': f'0x{word:08X}',
            'sf': (word >> 19) & 1, 'shift_bits': 12 if word & (1 << 19) else 0,
            'mx': mx, 'matrix': MATRIX[mx],
            'v': vx, 'vector': VECTOR[vx],
            'cv': cv, 'translation': TRANSLATION[cv],
            'lm': (word >> 10) & 1,
            'known_original_word': word == EXPECTED_COMMAND_WORD}


def audit_executable(image, base, pc=HELPER_COMMAND_PC):
    if pc < base or pc + 4 > base + len(image) or (pc - base) % 4:
        return {'command_pc': f'0x{pc:08X}', 'matched_original_command': False,
                'command': None}
    word = struct.unpack_from('<I', image, pc-base)[0]
    decoded = decode_mvmva(word)
    return {'command_pc': f'0x{pc:08X}',
            'matched_original_command': word == EXPECTED_COMMAND_WORD,
            'command': decoded}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path)
    args = p.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(audit_executable(image, base), indent=2))


if __name__ == '__main__':
    main()
