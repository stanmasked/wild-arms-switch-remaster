#!/usr/bin/env python3
"""Verify the original PS-X EXE's packed 4096-entry sin/cos table in place.

No copyrighted lookup table data is printed or embedded in source/tests.
"""
import argparse
import json
import math
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

TABLE = 0x800CBE44
ENTRIES = 4096
BUILDER = 0x800B7118
BUILDER_END = 0x800B739C
TABLE_LOAD_PCS = (0x800B7140, 0x800B7168, 0x800B71A4,
                  0x800B71CC, 0x800B7230, 0x800B7264)


def signed16(n):
    return n - 0x10000 if n & 0x8000 else n


def indexed_lookup(image, base, pc, table=TABLE):
    """Verify LUI scratch, ADDU scratch,scratch,index, LW scratch,low(scratch)."""
    if pc < base + 8 or pc + 4 > base + len(image) or (pc-base) % 4:
        return False
    w0, w1, w2 = struct.unpack_from('<3I', image, pc-base-8)
    if w0 >> 26 != 15 or w2 >> 26 != 35:
        return False
    temp = (w0 >> 16) & 31
    if ((w0 >> 21) & 31) != 0 or (w1 >> 26) != 0 or (w1 & 63) != 33:
        return False
    rs, rt, rd = (w1 >> 21) & 31, (w1 >> 16) & 31, (w1 >> 11) & 31
    if rd != temp or temp not in (rs, rt) or (w1 >> 6) & 31:
        return False
    if (w2 >> 21) & 31 != temp:
        return False
    address = (((w0 & 0xffff) << 16) + signed16(w2 & 0xffff)) & 0xffffffff
    return address == table


def analyze(image, base, table=TABLE, entries=ENTRIES, pcs=TABLE_LOAD_PCS):
    if entries < 4 or entries % 4:
        raise ValueError('entry count must be a positive multiple of four')
    start = table - base
    if start < 0 or start + entries*4 > len(image):
        return {'table_in_image': False, 'table_address':f'0x{table:08X}',
                'complete_lookup_chain_count': 0, 'values_emitted': False}
    values = [struct.unpack_from('<hh', image, start + 4*i) for i in range(entries)]
    q = entries//4
    cardinal = [values[i] for i in (0,q,2*q,3*q)]
    expected = [(0,4096),(4096,0),(0,-4096),(-4096,0)]
    maxerr = 0
    for i,(s,c) in enumerate(values):
        angle = 2*math.pi*i/entries
        maxerr = max(maxerr, abs(s-round(4096*math.sin(angle))),
                     abs(c-round(4096*math.cos(angle))))
    verified_pcs = [f'0x{pc:08X}' for pc in pcs if indexed_lookup(image,base,pc,table)]
    return {'table_in_image': True, 'table_address':f'0x{table:08X}',
            'entries':entries, 'byte_length':entries*4,
            'layout':'signed int16 sine low; signed int16 cosine high',
            'cardinal_points_match':cardinal == expected,
            'max_abs_error_against_rounded_trig':maxerr,
            'lookup_instructions_checked':len(pcs),
            'complete_lookup_chain_count':len(verified_pcs),
            'verified_lookup_pcs':verified_pcs,
            'values_emitted':False,
            'bit_exact_table_generation_algorithm_known':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path,help='private extracted original PS-X EXE')
    args = parser.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(analyze(image,base),indent=2))

if __name__=='__main__':main()
