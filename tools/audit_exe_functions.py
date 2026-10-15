#!/usr/bin/env python3
"""Read-only opcode-category audit of PS-X EXE call targets; no assets exported."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
TARGETS = (0x8006d258, 0x8006dca0, 0x8006dcec)

def read_exe(image, entry):
    result = bytearray()
    with open(image, 'rb') as f:
        for i in range((entry['size'] + 2047)//2048):
            f.seek((entry['lba'] + i)*2352)
            sector = f.read(2352)
            if len(sector) != 2352 or sector[:12] != SYNC:
                raise ValueError('invalid CD sector sync')
            if sector[15] != 2 or sector[18] & 0x20 or sector[16:20] != sector[20:24]:
                raise ValueError('expected MODE2/Form1 sector')
            result.extend(sector[24:2072])
    return bytes(result[:entry['size']])

def exe_info(data):
    if len(data) < 2048 or data[:8] != b'PS-X EXE':
        raise ValueError('invalid PS-X EXE')
    base = int.from_bytes(data[0x18:0x1c], 'little')
    length = int.from_bytes(data[0x1c:0x20], 'little')
    if not length or length + 2048 > len(data):
        raise ValueError('truncated EXE payload')
    return base, length

def kind(word):
    op = word >> 26
    if word == 0x03e00008: return 'jr_ra'
    if op == 3: return 'jal'
    if op == 2: return 'j'
    if op in (1, 4, 5, 6, 7): return 'branch_candidate'
    if op in (40, 41, 42, 43, 46, 47): return 'store'
    if op in (32, 33, 34, 35, 36, 37, 38, 39): return 'load'
    if op == 15: return 'lui'
    return 'other'

def inspect(data, addresses=TARGETS, window=0x50):
    base, length = exe_info(data)
    if window <= 0 or window > 4096 or window % 4:
        raise ValueError('invalid window')
    results = []
    for address in addresses:
        if address < base or address >= base + length or address % 4:
            raise ValueError('target outside EXE')
        pos = 2048 + address - base
        words = [int.from_bytes(data[i:i+4], 'little')
                 for i in range(pos, min(2048 + length, pos + window), 4)]
        kinds = [kind(word) for word in words]
        first_return = next((address + i*4 for i, k in enumerate(kinds)
                             if k == 'jr_ra'), None)
        results.append({
            'address': f'0x{address:08x}',
            'iso_exe_file_offset': pos,
            'first_jr_ra': f'0x{first_return:08x}' if first_return else None,
            'shared_index_prefix': words[:2] == [0x00051080, 0x00451021],
            'opcode_kinds': {k: kinds.count(k) for k in sorted(set(kinds))}
        })
    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('inventory', help='JSON from inspect_disc.py --json')
    ap.add_argument('--window', type=lambda value: int(value, 0), default=0x50)
    args = ap.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    matched = [e for e in entries if e['path'] == '/EXE/WILDARMS.EXE;1' and not e['directory']]
    if len(matched) != 1:
        ap.error('WILDARMS.EXE not found')
    print(json.dumps({'functions': inspect(read_exe(args.image, matched[0]),
                                           window=args.window)}, indent=2))

if __name__ == '__main__':
    main()
