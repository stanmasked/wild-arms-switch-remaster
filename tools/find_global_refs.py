#!/usr/bin/env python3
"""Read-only exact adjacent LUI+load/store references in PS-X EXE."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
LOADS = {32, 33, 35, 36, 37}
STORES = {40, 41, 43}

def scan_pairs(code, load_base, address):
    if len(code) % 4:
        raise ValueError('unaligned code')
    upper = (address >> 16) & 0xffff
    lower = address & 0xffff
    if lower >= 0x8000:
        upper = (upper + 1) & 0xffff
    words = [int.from_bytes(code[i:i+4], 'little') for i in range(0, len(code), 4)]
    result = []
    for i in range(len(words)-1):
        a, b = words[i], words[i+1]
        if a >> 26 != 15 or a & 0xffff != upper:
            continue
        reg, op = (a >> 16) & 31, b >> 26
        if ((b >> 21) & 31) != reg or (b & 0xffff) != lower:
            continue
        if op in LOADS or op in STORES:
            result.append({'lui_pc': f'0x{load_base+4*i:08x}',
                           'memory_pc': f'0x{load_base+4*(i+1):08x}',
                           'kind': 'store' if op in STORES else 'load', 'opcode': op})
    return result

def read_exe(image, entry):
    raw = bytearray()
    with open(image, 'rb') as stream:
        for i in range((entry['size']+2047)//2048):
            stream.seek((entry['lba']+i)*2352)
            s = stream.read(2352)
            if len(s) != 2352 or s[:12] != SYNC or s[15] != 2:
                raise ValueError('invalid MODE2 sector')
            if s[18] & 0x20 or s[16:20] != s[20:24]:
                raise ValueError('not XA Form1')
            raw.extend(s[24:2072])
    raw = bytes(raw[:entry['size']])
    if raw[:8] != b'PS-X EXE':
        raise ValueError('not PS-X EXE')
    base = int.from_bytes(raw[0x18:0x1c], 'little')
    length = int.from_bytes(raw[0x1c:0x20], 'little')
    if len(raw) < 2048+length or length % 4:
        raise ValueError('truncated or unaligned EXE load image')
    return base, raw[2048:2048+length]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('disc', help='User-owned raw MODE2/Form1 BIN')
    p.add_argument('inventory', help='Output of inspect_disc.py --json')
    p.add_argument('--address', type=lambda v: int(v,0), default=0x800d2c3c)
    args = p.parse_args()
    e = next(x for x in json.loads(Path(args.inventory).read_text())['entries']
             if x['path'] == '/EXE/WILDARMS.EXE;1')
    base, code = read_exe(args.disc, e)
    matches = scan_pairs(code, base, args.address)
    print(json.dumps({'address': f'0x{args.address:08x}',
                      'exe_load_end_exclusive': f'0x{base+len(code):08x}',
                      'distance_beyond_exe_load_end': args.address-(base+len(code)),
                      'strict_adjacent_matches': len(matches),
                      'loads': sum(x['kind']=='load' for x in matches),
                      'stores': sum(x['kind']=='store' for x in matches),
                      'references': matches}, indent=2))
if __name__ == '__main__':
    main()
