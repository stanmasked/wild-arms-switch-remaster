#!/usr/bin/env python3
"""Read-only signature check for Wild Arms USA record field +0x54."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff'*10 + b'\x00'
CHECK = {
    0x80078e30: 0x3c03800d, 0x80078e34: 0x8c632cec,
    0x80078e38: 0x00041040, 0x80078e3c: 0x00441021,
    0x80078e40: 0x000210c0, 0x80078e44: 0x00621821,
    0x80078e48: 0x02001021, 0x80078e4c: 0xae030054,
}

def verify(exe):
    if len(exe) < 2048 or exe[:8] != b'PS-X EXE':
        raise ValueError('invalid PS-X EXE')
    base = int.from_bytes(exe[0x18:0x1c], 'little')
    size = int.from_bytes(exe[0x1c:0x20], 'little')
    if size == 0 or 2048+size > len(exe):
        raise ValueError('truncated load image')
    for pc, word in CHECK.items():
        off = 2048+pc-base
        if off < 2048 or off+4 > 2048+size or int.from_bytes(exe[off:off+4], 'little') != word:
            raise ValueError(f'instruction mismatch at {pc:#x}')
    return {'checked_words':len(CHECK), 'destination':'memory32[s0+0x54]',
            'global_source':'0x800D2CEC',
            'stored_expression':'memory32[0x800D2CEC] + 24*a0 (mod 2^32)',
            'return_value':'v0=s0'}

def read_exe(image, entry):
    out = bytearray()
    with open(image, 'rb') as disc:
        for i in range((entry['size']+2047)//2048):
            disc.seek((entry['lba']+i)*2352)
            s = disc.read(2352)
            if (len(s) != 2352 or s[:12] != SYNC or s[15] != 2 or
                    s[18] & 0x20 or s[16:20] != s[20:24]):
                raise ValueError('not MODE2/Form1')
            out.extend(s[24:2072])
    return bytes(out[:entry['size']])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('inventory', help='inspect_disc.py --json')
    args=ap.parse_args()
    records=json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    selected=[e for e in records if e['path']=='/EXE/WILDARMS.EXE;1' and not e['directory']]
    if len(selected)!=1:
        ap.error('main EXE not found')
    print(json.dumps(verify(read_exe(args.image,selected[0])), indent=2))

if __name__=='__main__':
    main()
