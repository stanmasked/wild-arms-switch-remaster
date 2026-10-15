#!/usr/bin/env python3
"""Find direct callers of polygon-cursor setup functions and argument-a0 sources.

Static, bounded predecessor inspection, not a path-sensitive control-flow proof.
Never exports the original executable, only derived instruction addresses.
"""
import argparse
import json
import struct
from pathlib import Path

try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_callers import direct_calls
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_callers import direct_calls

# Identified function entry points (not arbitrary NCLIP instruction addresses).
CURSOR_FUNCTION_ENTRIES = (0x80076908, 0x80076B88, 0x80076F40)


def decode_argument_a0(word):
    """Recognize complete a0 definitions, preserving register and signed displacement."""
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    imm = word & 0xFFFF
    if op in (8, 9) and rt == 4:
        return {'kind': 'ADDI' if op == 8 else 'ADDIU',
                'source_register': rs, 'signed_displacement': imm-65536 if imm >= 32768 else imm}
    if op == 0 and (word & 63) in (0x21, 0x20) and ((word >> 6) & 31) == 0 and rd == 4:
        return {'kind': 'ADDU' if (word & 63) == 0x21 else 'ADD',
                'source_registers': [rs, rt]}
    if op == 35 and rt == 4:
        return {'kind': 'LW', 'base_register': rs,
                'signed_displacement': imm-65536 if imm >= 32768 else imm}
    return None


def last_argument_write(image, base, call, window=16):
    if call < base or call + 4 > base + len(image) or (call-base)%4:
        raise ValueError('JAL call address outside aligned executable')
    for address in range(call-4, max(base,call-4*window)-4,-4):
        word = struct.unpack_from('<I',image,address-base)[0]
        decoded = decode_argument_a0(word)
        if decoded is not None:
            return {'address': f'0x{address:08X}', **decoded}
    return None


def audit(image, base, targets=CURSOR_FUNCTION_ENTRIES):
    calls = direct_calls(image, base)
    records = []
    for target in targets:
        sites = calls.get(target, [])
        records.append({'function_entry': f'0x{target:08X}',
                        'calls': [{'jal': f'0x{call:08X}',
                                   'last_a0_definition': last_argument_write(image,base,call)}
                                  for call in sites]})
    return {'target_functions':len(records),
            'direct_jal_calls':sum(len(r['calls']) for r in records),
            'records':records,'runtime_structure_data_recovered':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit(image,base),indent=2))

if __name__=='__main__':main()
