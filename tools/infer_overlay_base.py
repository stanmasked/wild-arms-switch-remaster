#!/usr/bin/env python3
"""Infer PS1 overlay base from MIPS relative branch and direct jump evidence."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

def read_prefix(image, record, count):
    if count <= 0 or count > 1024 * 1024:
        raise ValueError('prefix size out of bounds')
    result = bytearray()
    with open(image, 'rb') as f:
        for i in range((min(record['size'], count) + 2047) // 2048):
            f.seek((record['lba'] + i) * 2352)
            sector = f.read(2352)
            if len(sector) != 2352 or sector[:12] != SYNC:
                raise ValueError('invalid raw CD sector sync')
            if sector[15] != 2 or sector[18] & 0x20 or sector[16:20] != sector[20:24]:
                raise ValueError('expected MODE2/Form1 sector')
            result.extend(sector[24:2072])
    return bytes(result[:min(record['size'], count)])

def word(data, offset):
    if offset < 0 or offset + 4 > len(data) or offset % 4:
        raise ValueError('invalid word offset')
    return int.from_bytes(data[offset:offset+4], 'little')

def branch_target(instruction, offset):
    if instruction >> 26 not in (4, 5, 6, 7):
        raise ValueError('expected MIPS conditional branch')
    immediate = instruction & 0xffff
    if immediate >= 0x8000:
        immediate -= 0x10000
    return offset + 4 + immediate * 4

def jump_low_target(instruction):
    if instruction >> 26 not in (2, 3):
        raise ValueError('expected MIPS J or JAL')
    return (instruction & 0x03ffffff) << 2

def infer_base(data, branch_offset=0x64, jump_offset=0xf4):
    branch = branch_target(word(data, branch_offset), branch_offset)
    jump = jump_low_target(word(data, jump_offset))
    base_low28 = (jump - branch) & 0x0fffffff
    # High nibble assumed from independent KSEG0 pointers in the overlay.
    base = 0x80000000 | base_low28
    header = [word(data, i) for i in range(0, 28, 4)]
    return {
        'branch_target_file_offset': branch,
        'jump_encoded_low28_target': f'0x{jump:07x}',
        'base_candidate': f'0x{base:08x}',
        'header_offsets_if_base_correct': [v-base for v in header],
        'header_pointers_within_prefix': all(base <= v < base + len(data) for v in header),
        'branch_target_bytes_available': 0 <= branch <= len(data)-4
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory', help='Output of inspect_disc.py --json')
    p.add_argument('--file', default='/BIN/CDGD.BIN;1')
    args = p.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    matches = [e for e in entries if e['path'] == args.file and not e['directory']]
    if len(matches) != 1:
        p.error('selected ISO file not found')
    print(json.dumps({'file': args.file,
                      **infer_base(read_prefix(args.image, matches[0], 0x800))}, indent=2))

if __name__ == '__main__':
    main()
