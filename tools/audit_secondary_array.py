#!/usr/bin/env python3
"""Read-only signature audit of references to secondary global 0x800D2CEC."""
import argparse
import json
from pathlib import Path

SYNC=b'\x00'+b'\xff'*10+b'\x00'
PATTERNS={
 0x80078d18:(0x3c02800d,0x8c422cec,0x00033040,0x00c33021,0x000630c0,0x0c01ddbc,0x00463021),
 0x80078e30:(0x3c03800d,0x8c632cec,0x00041040,0x00441021,0x000210c0,0x00621821,0x02001021,0xae030054)
}

def inspect_exe(exe):
    if len(exe)<2048 or exe[:8]!=b'PS-X EXE':
        raise ValueError('invalid PS-X EXE')
    base=int.from_bytes(exe[0x18:0x1c],'little')
    size=int.from_bytes(exe[0x1c:0x20],'little')
    if not size or 2048+size>len(exe):
        raise ValueError('truncated EXE')
    for pc,pattern in PATTERNS.items():
        off=2048+pc-base
        if off<2048 or off+len(pattern)*4>2048+size:
            raise ValueError('signature beyond EXE image')
        actual=tuple(int.from_bytes(exe[off+i*4:off+i*4+4],'little')
                     for i in range(len(pattern)))
        if actual!=pattern:
            raise ValueError(f'instruction mismatch at {pc:#x}')
    return {'global_variable':'0x800D2CEC',
            'verified_instruction_words':15,
            'immediate_load_sites':['0x80078D1C','0x80078E34'],
            'site_80078D1C':{'scale':24,'index_register':'v1',
                'argument_register':'a2','next_call':'0x800776F0',
                'delay_slot':'addu a2,v0,a2'},
            'site_80078E34':{'scale':24,'index_register':'a0',
                'destination':'word at s0+0x54'}}

def read_exe(image,entry):
    if not 2048<=entry['size']<=4*1024*1024: raise ValueError('invalid EXE extent')
    result=bytearray()
    with open(image,'rb') as f:
        for i in range((entry['size']+2047)//2048):
            f.seek((entry['lba']+i)*2352)
            sec=f.read(2352)
            if (len(sec)!=2352 or sec[:12]!=SYNC or sec[15]!=2 or
                sec[18]&0x20 or sec[16:20]!=sec[20:24]):
                raise ValueError('not a valid MODE2/Form1 sector')
            result.extend(sec[24:2072])
    return bytes(result[:entry['size']])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('disc')
    p.add_argument('inventory',help='JSON from inspect_disc.py --json')
    args=p.parse_args()
    entries=json.loads(Path(args.inventory).read_text(encoding='utf8'))['entries']
    e=[x for x in entries if x['path']=='/EXE/WILDARMS.EXE;1' and not x['directory']]
    if len(e)!=1:p.error('WILDARMS.EXE not found')
    print(json.dumps(inspect_exe(read_exe(args.disc,e[0])),indent=2))

if __name__=='__main__': main()
