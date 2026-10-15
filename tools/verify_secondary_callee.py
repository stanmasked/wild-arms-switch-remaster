"""Read-only exact MIPS signature verification for Wild Arms USA EXE."""
import argparse
import json
from pathlib import Path

ENTRY=0x800776F0
SIGNATURE={
  0x800776F0:0x27BDFFA0,
  0x800776F8:0x0080B821,
  0x80077700:0x00C0B021,
  0x80077708:0x00E0A821,
  0x8007772C:0x86E20052,
  0x80077730:0x8CB10000,
  0x80077734:0x1040005D,
  0x80077768:0x0C02DC3A,
  0x80077780:0x0C02DC3A,
}
SYNC=b'\x00'+b'\xff'*10+b'\x00'

def verify(exe):
    if len(exe)<2048 or exe[:8]!=b'PS-X EXE':
        raise ValueError('invalid PS-X EXE')
    base=int.from_bytes(exe[0x18:0x1c],'little')
    size=int.from_bytes(exe[0x1c:0x20],'little')
    if size==0 or 2048+size>len(exe):
        raise ValueError('invalid EXE payload')
    for pc,expected in SIGNATURE.items():
        offset=2048+pc-base
        if offset<2048 or offset+4>2048+size:
            raise ValueError('address outside EXE')
        if int.from_bytes(exe[offset:offset+4],'little')!=expected:
            raise ValueError(f'instruction mismatch at {pc:#x}')
    return {'entry':f'0x{ENTRY:08X}', 'checked_instructions':len(SIGNATURE),
            'a0_saved_in':'s7','a2_saved_in':'s6','a3_saved_in':'s5',
            'halfword_read':'lh v0,0x52(s7)', 'word_read':'lw s1,0(a1)',
            'helper_calls':['0x800B70E8','0x800B70E8']}

def read_entry(image,entry):
    if not 2048<=entry['size']<=4*1024*1024:
        raise ValueError('invalid EXE size')
    out=bytearray()
    with open(image,'rb') as stream:
        for i in range((entry['size']+2047)//2048):
            stream.seek((entry['lba']+i)*2352)
            sector=stream.read(2352)
            if (len(sector)!=2352 or sector[:12]!=SYNC or sector[15]!=2
                or sector[18]&0x20 or sector[16:20]!=sector[20:24]):
                raise ValueError('not MODE2/Form1')
            out.extend(sector[24:2072])
    return bytes(out[:entry['size']])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('image')
    parser.add_argument('inventory',help='JSON from inspect_disc.py --json')
    args=parser.parse_args()
    entries=json.loads(Path(args.inventory).read_text(encoding='utf8'))['entries']
    found=[e for e in entries if e['path']=='/EXE/WILDARMS.EXE;1' and not e['directory']]
    if len(found)!=1:parser.error('main EXE not found')
    print(json.dumps(verify(read_entry(args.image,found[0])),indent=2))

if __name__=='__main__':
    main()
