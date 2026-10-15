#!/usr/bin/env python3
"""Read-only PS-X EXE declared memory-range audit from original MODE2/Form1 CD image."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

def parse_header(header, target=0x800d2c3c):
    if len(header) < 2048 or header[:8] != b'PS-X EXE':
        raise ValueError('invalid PS-X EXE header')
    def u32(offset):
        return int.from_bytes(header[offset:offset+4], 'little')
    load, size, bss, bss_size = (u32(i) for i in (0x18, 0x1c, 0x28, 0x2c))
    if not size or load + size > 0x100000000:
        raise ValueError('invalid image extent')
    declared_bss = bool(bss and bss_size)
    return {
        'load_start': f'0x{load:08x}',
        'load_end_exclusive': f'0x{load+size:08x}',
        'bss_address': f'0x{bss:08x}',
        'bss_size': bss_size,
        'declared_bss': declared_bss,
        'target': f'0x{target:08x}',
        'target_in_load_image': load <= target < load + size,
        'target_in_declared_bss': bool(declared_bss and bss <= target < bss+bss_size),
        'target_distance_from_image_end': target - (load+size),
    }

def read_header(image, entry):
    if entry['size'] < 2048:
        raise ValueError('EXE smaller than header')
    with open(image, 'rb') as disc:
        disc.seek(entry['lba'] * 2352)
        sector = disc.read(2352)
    if len(sector) != 2352 or sector[:12] != SYNC:
        raise ValueError('bad CD sync')
    if sector[15] != 2 or sector[18] & 0x20 or sector[16:20] != sector[20:24]:
        raise ValueError('expected MODE2/Form1 XA sector')
    return sector[24:2072]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image', help='User-owned raw 2352-byte BIN image')
    p.add_argument('inventory', help='JSON from inspect_disc.py --json')
    p.add_argument('--target', type=lambda x: int(x, 0), default=0x800d2c3c)
    args = p.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    matches = [e for e in entries if e['path'] == '/EXE/WILDARMS.EXE;1' and not e['directory']]
    if len(matches) != 1:
        p.error('WILDARMS.EXE not found')
    print(json.dumps(parse_header(read_header(args.image, matches[0]), args.target), indent=2))

if __name__ == '__main__':
    main()
