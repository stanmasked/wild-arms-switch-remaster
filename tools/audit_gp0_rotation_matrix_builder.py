#!/usr/bin/env python3
"""Locate SH writes of the original PS1 rotation-matrix constructor.

Static instruction evidence only; not a claim about trigonometric values.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

BUILDER = 0x800B7118
RETURN = 0x800B739C
CALL = 0x80077980
ROTATION_LOADER_CALL = 0x80077988
EXPECTED_HALFWORDED_OFFSETS = tuple(range(0, 18, 2))


def sw_halfword(word):
    if word >> 26 != 0x29:
        return None
    imm = word & 65535
    return {'base': (word >> 21) & 31, 'value_register': (word >> 16) & 31,
            'offset': imm - 65536 if imm & 0x8000 else imm}


def jal_target(word, address):
    if word >> 26 != 3:
        return None
    return ((address + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2)


def global_lw_address(lui, lw):
    if lui >> 26 != 15 or lw >> 26 != 35:
        return None
    reg = (lui >> 16) & 31
    if ((lui >> 21) & 31) != 0 or ((lw >> 21) & 31) != reg:
        return None
    offset = lw & 65535
    offset = offset-65536 if offset & 0x8000 else offset
    return (((lui & 65535) << 16) + offset) & 0xffffffff


def analyze(image, base, start=BUILDER, end=RETURN, call=CALL):
    if start < base or end+4 > base+len(image) or (start-base) % 4 or (end-base) % 4:
        return {'valid_range': False, 'matrix_halfword_offsets': [], 'complete_matrix_slots': False}
    writes=[]
    table_reads=[]
    for address in range(start, end+4, 4):
        word = struct.unpack_from('<I', image, address-base)[0]
        decoded = sw_halfword(word)
        if decoded and decoded['base'] == 5 and 0 <= decoded['offset'] < 18:
            writes.append({'address': f'0x{address:08X}', **decoded})
        if address >= start+8 and word >> 26 == 35:
            # LUI and LW need not be adjacent: tolerate one instruction between.
            for gap in (4,8):
                prev = struct.unpack_from('<I', image, address-base-gap)[0]
                lookup = global_lw_address(prev, word)
                if lookup is not None and lookup == 0x800CBE44:
                    table_reads.append(f'0x{address:08X}')
                    break
    calls_found=False
    pointer_from_stack=False
    if base <= call and call+8 <= base+len(image):
        word=struct.unpack_from('<I',image,call-base)[0]
        calls_found=jal_target(word,call)==start
        # a1=sp+16 at 0x80077970
        ptraddr=call-16
        if ptraddr >= base:
            p=struct.unpack_from('<I',image,ptraddr-base)[0]
            pointer_from_stack=(p>>26 in (8,9) and ((p>>21)&31)==29
                                and ((p>>16)&31)==5 and (p&65535)==16)
    offsets=sorted(set(w['offset'] for w in writes))
    return {'valid_range': True,'builder':f'0x{start:08X}',
            'builder_called':calls_found, 'a1_is_stack_plus_16':pointer_from_stack,
            'matrix_halfword_offsets':offsets,
            'matrix_halfword_writes':writes,
            'complete_matrix_slots':tuple(offsets)==EXPECTED_HALFWORDED_OFFSETS,
            'global_table_pointer_slot': '0x800CBE44' if table_reads else None,
            'global_pointer_load_instructions':table_reads,
            'runtime_coefficients_recovered':False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    args=ap.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(analyze(image,base),indent=2))

if __name__=='__main__':main()
