#!/usr/bin/env python3
"""Read-only MIPS R3000 control-flow scan of PS1 MODE2/Form1 files.

Jump fields are NOT assumed to be file offsets or complete addresses.
"""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
BRANCHES = {4: 'beq', 5: 'bne', 6: 'blez', 7: 'bgtz'}
REGIMM = {0: 'bltz', 1: 'bgez', 16: 'bltzal', 17: 'bgezal'}

def classify(word, offset):
    op = word >> 26
    if op in (2, 3):
        return {'offset': offset, 'op': 'j' if op == 2 else 'jal',
                'target_field': f'0x{word & 0x03ffffff:07x}',
                'note': 'full virtual target requires runtime PC upper bits'}
    if op in BRANCHES or (op == 1 and ((word >> 16) & 31) in REGIMM):
        name = BRANCHES.get(op) if op != 1 else REGIMM[(word >> 16) & 31]
        imm = word & 0xffff
        if imm & 0x8000:
            imm -= 0x10000
        return {'offset': offset, 'op': name,
                'relative_target': offset + 4 + imm * 4}
    if op == 0 and (word & 63) == 8 and (word & 0x001fffc0) == 0:
        return {'offset': offset, 'op': 'jr', 'register': (word >> 21) & 31}
    if op == 0 and (word & 63) == 9 and (word & 0x001f07c0) == 0:
        return {'offset': offset, 'op': 'jalr', 'register': (word >> 21) & 31}
    return None

def scan(data, first_offset=0, limit=512):
    if first_offset < 0 or first_offset % 4:
        raise ValueError('first_offset must be a nonnegative multiple of 4')
    end = min(len(data), first_offset + limit)
    matches = []
    for off in range(first_offset, end - 3, 4):
        item = classify(int.from_bytes(data[off:off+4], 'little'), off)
        if item:
            matches.append(item)
    return matches

def read_form1_prefix(image, entry, length):
    length = min(length, entry['size'])
    output = bytearray()
    with open(image, 'rb') as source:
        for i in range((length + 2047) // 2048):
            source.seek((entry['lba'] + i) * 2352)
            sector = source.read(2352)
            if len(sector) != 2352 or sector[:12] != SYNC:
                raise ValueError('invalid raw CD sector sync')
            if sector[15] != 2 or sector[18] & 0x20 or sector[16:20] != sector[20:24]:
                raise ValueError('not valid MODE2/Form1 XA sector')
            output.extend(sector[24:2072])
    return bytes(output[:length])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('inventory', help='JSON from inspect_disc.py --json')
    ap.add_argument('--path', default='/BIN/CDGD.BIN;1')
    ap.add_argument('--start', type=lambda v: int(v, 0), default=0x1c)
    ap.add_argument('--length', type=lambda v: int(v, 0), default=0x200)
    args = ap.parse_args()
    inventory = json.loads(Path(args.inventory).read_text(encoding='utf-8'))
    matches = [e for e in inventory['entries'] if e['path'] == args.path and not e['directory']]
    if len(matches) != 1 or args.length < 0 or args.length > 1024 * 1024:
        ap.error('invalid file path or length')
    data = read_form1_prefix(args.image, matches[0], args.start + args.length)
    result = scan(data, args.start, args.length)
    print(json.dumps({'file': args.path, 'start': args.start,
                      'end': min(len(data), args.start + args.length),
                      'control_flow_candidates': result}, indent=2))

if __name__ == '__main__':
    main()
