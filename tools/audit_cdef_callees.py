#!/usr/bin/env python3
"""Read-only analysis of three candidate CDEF call targets in a PS-X EXE."""
import argparse
import json
from pathlib import Path

TARGETS = (0x8007d564, 0x800641e0, 0x80078db0)
SYNC = b'\x00' + b'\xff'*10 + b'\x00'

def read_exe(disc, entry):
    result = bytearray()
    with open(disc, 'rb') as f:
        for i in range((entry['size'] + 2047)//2048):
            f.seek((entry['lba']+i)*2352)
            sector=f.read(2352)
            if len(sector)!=2352 or sector[:12]!=SYNC or sector[15]!=2:
                raise ValueError('invalid raw MODE2 sector')
            if sector[18]&0x20 or sector[16:20]!=sector[20:24]:
                raise ValueError('not XA Form1')
            result.extend(sector[24:2072])
    return bytes(result[:entry['size']])

def psx_image(data):
    if len(data)<2048 or data[:8]!=b'PS-X EXE':
        raise ValueError('not PS-X EXE')
    load=int.from_bytes(data[0x18:0x1c],'little')
    size=int.from_bytes(data[0x1c:0x20],'little')
    if size<4 or 2048+size>len(data) or size%4:
        raise ValueError('invalid EXE payload')
    return load, data[2048:2048+size]

def examine(data, addresses=TARGETS, window=0x60):
    load, image = psx_image(data)
    if window<4 or window%4 or window>4096:
        raise ValueError('window must be multiple of 4, at most 4096')
    rows=[]
    for addr in addresses:
        off=addr-load
        if off<0 or off+window>len(image) or off%4:
            raise ValueError('target window outside load image')
        words=[int.from_bytes(image[off+i:off+i+4],'little')
               for i in range(0,window,4)]
        calls=[]
        memory=[]
        returns=[]
        for i,w in enumerate(words):
            pc=addr+i*4
            op=w>>26
            if op in (2,3):
                target=((pc+4)&0xf0000000)|((w&0x3ffffff)<<2)
                calls.append({'pc':f'0x{pc:08x}', 'kind':'jal' if op==3 else 'j',
                              'target':f'0x{target:08x}'})
            if op in (32,33,35,36,37,40,41,43):
                memory.append({'pc':f'0x{pc:08x}',
                               'kind':'store' if op in (40,41,43) else 'load',
                               'base_register':(w>>21)&31,
                               'offset_signed':((w&65535)-65536 if w&32768 else w&65535)})
            if w==0x03e00008:
                returns.append(f'0x{pc:08x}')
        rows.append({'entry':f'0x{addr:08x}',
                     'calls_in_window':calls,
                     'memory_ops_in_window':memory,
                     'jr_ra_locations':returns})
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory')
    p.add_argument('--window',type=lambda x:int(x,0),default=0x60)
    a=p.parse_args()
    entries=json.loads(Path(a.inventory).read_text(encoding='utf-8'))['entries']
    exe=next(x for x in entries if x['path']=='/EXE/WILDARMS.EXE;1')
    print(json.dumps(examine(read_exe(a.image,exe),window=a.window),indent=2))

if __name__=='__main__':
    main()
