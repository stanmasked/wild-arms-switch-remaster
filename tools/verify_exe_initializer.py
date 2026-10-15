#!/usr/bin/env python3
"""Read-only verification of the WILDARMS.EXE structure-initializer signature.

This checks exact instructions rather than interpreting arbitrary bytes as code.
MIPS JR RA executes the *next* instruction as its delay slot.
"""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff'*10 + b'\x00'
ENTRY = 0x8006ce70
EXPECTED = (
    0x24021000, 0xa4800008, 0xa4800006, 0xa4800004,
    0xac800010, 0xac80000c, 0xac800014, 0xac82001c,
    0xac820020, 0x03e00008, 0xac820024,
)

def verify(words):
    if tuple(words) != EXPECTED:
        raise ValueError('EXE signature differs; do not assume initializer semantics')
    writes=[]
    for i,w in enumerate(words):
        op=w>>26
        if op not in (41, 43):
            continue
        base=(w>>21)&31
        source=(w>>16)&31
        if base != 4 or source not in (0,2):
            raise ValueError('unexpected store operands')
        writes.append({'offset':f'0x{w&0xffff:02x}',
                       'width_bits':16 if op==41 else 32,
                       'value':0 if source==0 else 4096,
                       'delay_slot':i==len(words)-1})
    if len(writes)!=9:
        raise ValueError('unexpected store count')
    return {'entry':f'0x{ENTRY:08x}', 'instruction_words':len(words),
            'stores':writes, 'returns_via_jr_ra':True}

def read_exe_prefix(image, entry, end=2048+0xc1800):
    if entry['size'] < end:
        raise ValueError('EXE entry shorter than expected')
    out=bytearray()
    with open(image,'rb') as f:
        for i in range((end+2047)//2048):
            f.seek((entry['lba']+i)*2352)
            s=f.read(2352)
            if (len(s)!=2352 or s[:12]!=SYNC or s[15]!=2 or
                    s[18]&0x20 or s[16:20]!=s[20:24]):
                raise ValueError('not a valid MODE2/Form1 sector')
            out.extend(s[24:2072])
    return bytes(out[:end])

def from_executable(data):
    if data[:8] != b'PS-X EXE':
        raise ValueError('invalid PS-X EXE header')
    load=int.from_bytes(data[0x18:0x1c],'little')
    size=int.from_bytes(data[0x1c:0x20],'little')
    off=2048+ENTRY-load
    if off<2048 or off+len(EXPECTED)*4>min(len(data),2048+size):
        raise ValueError('initializer outside EXE payload')
    words=[int.from_bytes(data[off+i:off+i+4],'little')
           for i in range(0,len(EXPECTED)*4,4)]
    return verify(words)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('disc')
    p.add_argument('inventory',help='inspect_disc.py --json')
    args=p.parse_args()
    rows=json.loads(Path(args.inventory).read_text(encoding='utf8'))['entries']
    matches=[r for r in rows if r['path']=='/EXE/WILDARMS.EXE;1']
    if len(matches)!=1: p.error('WILDARMS.EXE not found')
    print(json.dumps(from_executable(read_exe_prefix(args.disc,matches[0])),indent=2))

if __name__=='__main__': main()
