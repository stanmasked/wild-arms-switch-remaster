"""Verify record-pointer return and subsequent +0x54 read in PS-X EXE."""
import argparse
import json
from pathlib import Path

EXPECTED = {
  0x80078E48:0x02001021,  # addu v0,s0,zero
  0x80078E64:0x03E00008,  # jr ra
  0x80078E68:0x00000000,  # return delay slot
  0x800791BC:0x0C01E36C,  # jal 0x80078DB0
  0x800791C0:0x24070001,  # JAL delay slot
  0x800791C4:0x00401821,  # addu v1,v0,zero
  0x800791C8:0x8C730054,  # lw s3,0x54(v1)
}
SYNC=b'\x00'+b'\xff'*10+b'\x00'

def check(exe):
    if len(exe)<2048 or exe[:8]!=b'PS-X EXE': raise ValueError('invalid EXE')
    load=int.from_bytes(exe[0x18:0x1c],'little')
    size=int.from_bytes(exe[0x1c:0x20],'little')
    if size==0 or 2048+size>len(exe): raise ValueError('invalid image size')
    for pc,w in EXPECTED.items():
        pos=2048+pc-load
        if pos<2048 or pos+4>2048+size or int.from_bytes(exe[pos:pos+4],'little')!=w:
            raise ValueError(f'MIPS signature mismatch at {pc:#x}')
    return {'verified_words':len(EXPECTED), 'returned_pointer':'v0 = s0',
            'caller_copy':'v1 = v0 at 0x800791C4',
            'field_read':'lw s3,0x54(v1) at 0x800791C8'}

def read_exe(image,entry):
    out=bytearray()
    with open(image,'rb') as f:
        for i in range((entry['size']+2047)//2048):
            f.seek((entry['lba']+i)*2352)
            s=f.read(2352)
            if len(s)!=2352 or s[:12]!=SYNC or s[15]!=2 or s[18]&0x20 or s[16:20]!=s[20:24]:
                raise ValueError('invalid MODE2/Form1 sector')
            out.extend(s[24:2072])
    return bytes(out[:entry['size']])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('image');p.add_argument('inventory')
    args=p.parse_args()
    rows=json.loads(Path(args.inventory).read_text(encoding='utf8'))['entries']
    matches=[e for e in rows if e['path']=='/EXE/WILDARMS.EXE;1' and not e['directory']]
    if len(matches)!=1:p.error('EXE missing')
    print(json.dumps(check(read_exe(args.image,matches[0])),indent=2))
if __name__=='__main__':main()
