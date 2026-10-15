#!/usr/bin/env python3
"""Verify 16-slot status-byte clearing loop in Wild Arms USA PS-X EXE."""
import argparse
import json
from pathlib import Path

ENTRY = 0x80078d84
EXPECTED = (0x3c03800d, 0x8c632c44, 0x2402000f, 0xa0600000,
            0x2442ffff, 0x0441fffd, 0x24630058, 0x3c01800d,
            0xac202eb0, 0x03e00008, 0x00000000)
SYNC = b'\x00' + b'\xff'*10 + b'\x00'

def verify(words):
    if tuple(words) != EXPECTED:
        raise ValueError('original function signature differs')
    # bgez v0,-3 at instruction 5 returns to the byte store at instruction 3.
    branch_target = 5 + 1 - 3
    assert branch_target == 3
    return {'entry':f'0x{ENTRY:08X}', 'pointer_variable':'0x800D2C44',
            'slot_count':16, 'stride_bytes':88, 'cleared_field_offset':0,
            'last_cleared_offset':15*88,
            'branch_delay_slot':'addiu v1,v1,88 executes on taken and not-taken branches',
            'other_global_cleared':'0x800D2EB0'}

def extract(image, entry):
    load_bytes=bytearray()
    with open(image,'rb') as disc:
        for i in range((entry['size']+2047)//2048):
            disc.seek((entry['lba']+i)*2352)
            s=disc.read(2352)
            if len(s)!=2352 or s[:12]!=SYNC or s[15]!=2 or s[18]&0x20 or s[16:20]!=s[20:24]:
                raise ValueError('invalid MODE2/Form1 sector')
            load_bytes.extend(s[24:2072])
    exe=bytes(load_bytes[:entry['size']])
    if exe[:8]!=b'PS-X EXE': raise ValueError('PS-X EXE signature absent')
    base=int.from_bytes(exe[0x18:0x1c],'little')
    image_size=int.from_bytes(exe[0x1c:0x20],'little')
    at=2048+ENTRY-base
    if at < 2048 or at + 4*len(EXPECTED) > min(len(exe),2048+image_size):
        raise ValueError('loop outside declared EXE load image')
    return [int.from_bytes(exe[at+4*i:at+4*i+4],'little') for i in range(len(EXPECTED))]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('disc')
    p.add_argument('inventory',help='inspect_disc.py --json')
    a=p.parse_args()
    entries=json.loads(Path(a.inventory).read_text())['entries']
    matches=[e for e in entries if e['path']=='/EXE/WILDARMS.EXE;1']
    if len(matches)!=1: p.error('WILDARMS.EXE missing')
    print(json.dumps(verify(extract(a.disc,matches[0])),indent=2))
if __name__=='__main__': main()
