"""Read-only original Wild Arms USA PS-X EXE GTE RTPS helper signature check."""
import argparse,json
from pathlib import Path
PC=0x800B70E8
EXPECTED=(0xC8800000,0xC8810004,0x00000000,0x4A180001,0xE8AE0000,
          0xE8C80000,0x4843F800,0x48029800,0xACE30000,0x03E00008,0x00021083)
SYNC=b'\x00'+b'\xff'*10+b'\x00'

def inspect_words(words):
    if tuple(words)!=EXPECTED:
        raise ValueError('GTE signature differs; RTPS interpretation not verified')
    return {'pc':f'0x{PC:08X}','instructions':len(words),'command':'RTPS',
            'sf':(words[3]>>19)&1,'lm':(words[3]>>10)&1,
            'input':'a0 -> GTE VXY0, VZ0',
            'output_sxy2':'memory32[a1]','output_ir0':'memory32[a2]',
            'output_flag':'memory32[a3]','return':'arithmetic SZ3 >> 2',
            'return_delay_slot':True}

def extract(image,entry):
    if not 2048<=entry['size']<=4*1024*1024:raise ValueError('unexpected EXE size')
    raw=bytearray()
    with open(image,'rb') as f:
        for i in range((entry['size']+2047)//2048):
            f.seek((entry['lba']+i)*2352);s=f.read(2352)
            if len(s)!=2352 or s[:12]!=SYNC or s[15]!=2 or s[18]&0x20 or s[16:20]!=s[20:24]:
                raise ValueError('not MODE2/Form1')
            raw.extend(s[24:2072])
    exe=bytes(raw[:entry['size']])
    if exe[:8]!=b'PS-X EXE':raise ValueError('not PS-X EXE')
    base=int.from_bytes(exe[0x18:0x1c],'little')
    size=int.from_bytes(exe[0x1c:0x20],'little')
    off=2048+PC-base
    if off<2048 or off+4*len(EXPECTED)>min(len(exe),2048+size):
        raise ValueError('GTE helper outside loaded EXE')
    return [int.from_bytes(exe[off+4*i:off+4*i+4],'little') for i in range(len(EXPECTED))]

def main():
    p=argparse.ArgumentParser();p.add_argument('disc');p.add_argument('inventory')
    a=p.parse_args()
    entries=json.loads(Path(a.inventory).read_text(encoding='utf8'))['entries']
    matches=[x for x in entries if x['path']=='/EXE/WILDARMS.EXE;1' and not x['directory']]
    if len(matches)!=1:p.error('main EXE not found')
    print(json.dumps(inspect_words(extract(a.disc,matches[0])),indent=2))
if __name__=='__main__':main()
