#!/usr/bin/env python3
"""Locate GTE screen-coordinate stores on the positive-MAC0 path after NCLIP.

A static disassembly heuristic only; never emits original game binaries.
"""
import argparse
import json
import struct
from pathlib import Path

try:
    from .audit_original_nclip_winding import inspect, parse_exe
except ImportError:
    from audit_original_nclip_winding import inspect, parse_exe


def swc2(word):
    """Decode SWC2 rt, signed_offset(base) or return None."""
    if word >> 26 != 0x3a:
        return None
    offset = word & 0xffff
    if offset >= 0x8000:
        offset -= 65536
    return (word >> 16 & 31, word >> 21 & 31, offset)


def describe(image, base, window=10):
    sites = inspect(image, base, window)['sites']
    for site in sites:
        site['sxy_stores'] = []
        site['complete_sxy_writes_on_fallthrough'] = False
        if not site['blez']:
            continue
        branch = int(site['blez'], 16)
        target = int(site['branch_target'], 16)
        if target <= branch+8 or target > base+len(image):
            continue
        # The instruction in the BLEZ delay slot executes on both paths.
        # Scan only the static fallthrough interval beginning at BLEZ+8.
        for address in range(branch+8, target, 4):
            word = struct.unpack_from('<I', image, address-base)[0]
            store = swc2(word)
            if store is None or store[0] not in (12, 13, 14):
                continue
            site['sxy_stores'].append({
                'address': f'0x{address:08X}',
                'register': f'SXY{store[0]-12}',
                'base_register': store[1], 'offset': store[2]
            })
        found = {item['register'] for item in site['sxy_stores']}
        site['complete_sxy_writes_on_fallthrough'] = (
            found == {'SXY0', 'SXY1', 'SXY2'})
    return {
        'nclip_count': len(sites),
        'mac0_blez_count': sum(bool(s['blez']) for s in sites),
        'mac0_blez_with_sxy_triplet': sum(s['complete_sxy_writes_on_fallthrough']
                                          for s in sites),
        'sites': sites
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path, help='local PS-X EXE; do not commit')
    parser.add_argument('--window', type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.window <= 64:
        parser.error('window must be 2..64')
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(describe(image, base, args.window), indent=2))


if __name__ == '__main__':
    main()
