#!/usr/bin/env python3
"""Static COP2 NCLIP -> MFC2 MAC0 -> BLEZ audit of a local PS-X EXE.
Provide an extracted EXE, not a raw 2352-byte-sector BIN. No game data output.
"""
import argparse
import json
import struct
from pathlib import Path

MASK = 0xfe00003f

def parse_exe(blob):
    if len(blob) < 2048 or blob[:8] != b'PS-X EXE':
        raise ValueError('not a PS-X EXE')
    base, size = struct.unpack_from('<II', blob, 0x18)
    if base & 3 or size & 3 or not size or size > len(blob) - 2048:
        raise ValueError('invalid or truncated PS-X load image')
    return base, blob[2048:2048+size]

def is_command(word, command):
    return word & MASK == 0x4a000000 | command

def mac0_move(word):
    if word >> 26 != 0x12 or (word >> 21) & 31 or (word >> 11) & 31 != 24:
        return None
    rt = (word >> 16) & 31
    return rt or None

def blez_source(word):
    if word >> 26 == 6 and (word >> 16) & 31 == 0:
        return (word >> 21) & 31
    return None

def inspect(image, base, window=10):
    words = list(struct.unpack(f'<{len(image)//4}I', image))
    nclip_sites, rtpt_sites = [], []
    for i, word in enumerate(words):
        if is_command(word, 0x30):
            rtpt_sites.append(f'0x{base+4*i:08X}')
        if not is_command(word, 0x06):
            continue
        site = {'nclip':f'0x{base+4*i:08X}', 'word':f'0x{word:08X}',
                'mac0_read':None, 'blez':None, 'branch_target':None}
        for j in range(i+1, min(len(words),i+window+1)):
            register = mac0_move(words[j])
            if register is None:
                continue
            site['mac0_read'] = f'0x{base+4*j:08X}'
            for k in range(j+1,min(len(words),i+window+1)):
                if blez_source(words[k]) == register:
                    offset = struct.unpack('<h',struct.pack('<H',words[k]&65535))[0]
                    site['blez'] = f'0x{base+4*k:08X}'
                    site['branch_target'] = f'0x{base+4*(k+1+offset):08X}'
                    break
            if site['blez']:
                break
        nclip_sites.append(site)
    return {'load_address':f'0x{base:08X}', 'rtpt_count':len(rtpt_sites),
            'rtpt_sites':rtpt_sites, 'nclip_count':len(nclip_sites),
            'nclip_with_mac0_blez':sum(bool(x['blez']) for x in nclip_sites),
            'sites':nclip_sites}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path,help='local extracted PS-X EXE')
    parser.add_argument('--window',type=int,default=10)
    args=parser.parse_args()
    if not 2<=args.window<=64:
        parser.error('window must be 2..64')
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(inspect(image,base,args.window),indent=2))

if __name__=='__main__':
    main()
