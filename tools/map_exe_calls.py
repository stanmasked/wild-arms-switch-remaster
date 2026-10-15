#!/usr/bin/env python3
"""Read-only PS-X EXE header and MIPS jump mapping for raw PS1 MODE2/Form1 images."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

def read_prefix(image, entry, count):
    if not 1 <= count <= 1048576:
        raise ValueError('prefix size out of range')
    out = bytearray()
    with open(image, 'rb') as f:
        for i in range((min(entry['size'], count) + 2047) // 2048):
            f.seek((entry['lba'] + i) * 2352)
            s = f.read(2352)
            if len(s) != 2352 or s[:12] != SYNC:
                raise ValueError('invalid raw sector sync')
            if s[15] != 2 or s[18] & 0x20 or s[16:20] != s[20:24]:
                raise ValueError('expected MODE2/Form1 CD-XA sector')
            out.extend(s[24:2072])
    return bytes(out[:min(entry['size'], count)])

def parse_psx_exe(header):
    if len(header) < 2048 or header[:8] != b'PS-X EXE':
        raise ValueError('invalid PS-X EXE header')
    def u32(o):
        return int.from_bytes(header[o:o+4], 'little')
    start, size = u32(0x18), u32(0x1c)
    if not size or start + size > 0xffffffff:
        raise ValueError('invalid EXE load range')
    return {'entry': u32(0x10), 'load_address': start, 'load_size': size,
            'load_end_exclusive': start + size, 'stack_pointer': u32(0x30)}

def map_jump(word, offset, base, exe):
    op = word >> 26
    if op not in (2, 3):
        return None
    pc = (base + offset) & 0xffffffff
    target = ((pc + 4) & 0xf0000000) | ((word & 0x03ffffff) << 2)
    if exe['load_address'] <= target < exe['load_end_exclusive']:
        location = 'main_exe'
        file_offset = 2048 + target - exe['load_address']
    elif base <= target < base + 0x200000:
        location = 'overlay_candidate'
        file_offset = None
    else:
        location = 'unknown'
        file_offset = None
    return {'offset': offset, 'op': 'j' if op == 2 else 'jal',
            'target': f'0x{target:08x}', 'location': location,
            'exe_iso_file_offset': file_offset}

def scan(data, exe, base, start, length):
    if start < 0 or start % 4 or length < 1:
        raise ValueError('invalid scan window')
    out = []
    for o in range(start, min(len(data), start+length)-3, 4):
        item = map_jump(int.from_bytes(data[o:o+4], 'little'), o, base, exe)
        if item:
            out.append(item)
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory', help='JSON from inspect_disc.py --json')
    p.add_argument('--overlay', default='/BIN/CDGD.BIN;1')
    p.add_argument('--exe', default='/EXE/WILDARMS.EXE;1')
    p.add_argument('--base', type=lambda v: int(v, 0), default=0x8017c000)
    p.add_argument('--start', type=lambda v: int(v, 0), default=0x1c)
    p.add_argument('--length', type=lambda v: int(v, 0), default=0x140)
    a = p.parse_args()
    if a.length < 1 or a.start < 0 or a.start + a.length > 1048576:
        p.error('invalid scan window')
    entries = {e['path']: e for e in json.loads(Path(a.inventory).read_text())['entries']
               if not e['directory']}
    exe = parse_psx_exe(read_prefix(a.image, entries[a.exe], 2048))
    data = read_prefix(a.image, entries[a.overlay], a.start+a.length)
    print(json.dumps({'exe': a.exe, 'header': exe, 'overlay': a.overlay,
                      'assumed_overlay_base': f'0x{a.base:08x}',
                      'jumps': scan(data, exe, a.base, a.start, a.length)}, indent=2))

if __name__ == '__main__':
    main()
