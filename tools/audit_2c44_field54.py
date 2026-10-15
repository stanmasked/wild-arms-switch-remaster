#!/usr/bin/env python3
"""Verify shared 0x800D2C44 / +0x54 accesses; read-only Wild Arms USA audit."""
import argparse, json
from pathlib import Path
SYNC=b'\x00'+b'\xff'*10+b'\x00'
SIGNATURES={
0x80078f80:0x3c03800d,0x80078f84:0x8c632c44,0x80078f8c:0x00761821,
0x80078fa0:0xac620010,0x80078fa4:0xac640014,0x80078fa8:0xac650018,
0x80078fac:0xac66001c,0x80078fb8:0x8c750054,
0x8007915c:0x3c03800d,0x80079160:0x8c632c44,
0x800791bc:0x0c01e36c,0x800791c8:0x8c730054,
0x80086cd4:0x3c02800d,0x80086cd8:0x8c422c44,0x80086ce4:0x8c440054}
def check_signature(exe):
    if len(exe)<2048 or exe[:8]!=b'PS-X EXE': raise ValueError('invalid PS-X EXE')
    base=int.from_bytes(exe[0x18:0x1c],'little')
    size=int.from_bytes(exe[0x1c:0x20],'little')
    if not size or 2048+size>len(exe): raise ValueError('truncated load image')
    for pc,expected in SIGNATURES.items():
        off=2048+pc-base
        if off<2048 or off+4>2048+size or int.from_bytes(exe[off:off+4],'little')!=expected:
            raise ValueError(f'instruction mismatch at {pc:08x}')
    return {'verified_instruction_count':len(SIGNATURES),
            'global_pointer':'0x800D2C44',
            'field_54_read_pcs':['0x80078FB8','0x800791C8','0x80086CE4'],
            'indexed_adjustment':'v1 += s6 at 0x80078F8C',
            'caller_saved_hazard':'JAL at 0x800791BC precedes LW 0x54(v1) at 0x800791C8',
            'writes_v1_offsets':[16,20,24,28]}
def read_entry(image,entry):
    if not 0<entry['size']<=4*1024*1024: raise ValueError('invalid image size')
    data=bytearray()
    with open(image,'rb') as f:
        for i in range((entry['size']+2047)//2048):
            f.seek((entry['lba']+i)*2352);s=f.read(2352)
            if len(s)!=2352 or s[:12]!=SYNC or s[15]!=2 or s[18]&0x20 or s[16:20]!=s[20:24]:
                raise ValueError('not MODE2/Form1')
            data.extend(s[24:2072])
    return bytes(data[:entry['size']])
def main():
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('inventory');a=p.parse_args()
    rows=json.loads(Path(a.inventory).read_text(encoding='utf-8'))['entries']
    e=[r for r in rows if r['path']=='/EXE/WILDARMS.EXE;1' and not r['directory']]
    if len(e)!=1:p.error('EXE not found')
    print(json.dumps(check_signature(read_entry(a.image,e[0])),indent=2))
if __name__=='__main__':main()
