#!/usr/bin/env python3
"""Conservative MIPS source proofs for root polygon structure registers.

Emit opcode address evidence only; the executable is never reproduced.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe


def decode(word):
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    imm = word & 0xffff
    imm_s = imm - 65536 if imm >= 32768 else imm
    if op == 15 and rs == 0:
        return ('LUI', rt, imm)
    if op == 35:
        return ('LW', rt, rs, imm_s)
    if op == 0 and (word & 63) == 0x21 and ((word >> 6) & 31) == 0:
        return ('ADDU', rd, rs, rt)
    return None


def source_at(image, base, address, dest, lookback=12):
    if address < base or address >= base + len(image) or (address-base)%4:
        raise ValueError('address outside aligned image')
    words = struct.unpack(f'<{len(image)//4}I', image)
    index=(address-base)//4
    ins=decode(words[index])
    if ins is None or ins[1] != dest:
        return None
    if ins[0] == 'ADDU' and ins[3] == 0:
        return {'kind':'incoming_register_copy','register':ins[2], 'at':f'0x{address:08X}'}
    if ins[0] != 'LW':
        return None
    for prior in range(index-1,max(-1,index-lookback-1),-1):
        candidate=decode(words[prior])
        if candidate and candidate[0] == 'LUI' and candidate[1] == ins[2]:
            address32=((candidate[2]<<16)+ins[3]) & 0xffffffff
            return {'kind':'global_pointer_load', 'global_address':f'0x{address32:08X}',
                    'lui_at':f'0x{base+4*prior:08X}', 'lw_at':f'0x{address:08X}',
                    'register':dest}
    return {'kind':'indirect_load_unresolved','base_register':ins[2],'offset':ins[3]}


def audit(image,base):
    checks=[('polygon_loop_r20',0x80077D20,20),
            ('polygon_loop_r22',0x80077D30,22),
            ('secondary_loop_r22',0x8007828C,22)]
    records=[]
    for name,address,reg in checks:
        if not base<=address<base+len(image):
            records.append({'name':name,'status':'out_of_image'})
            continue
        records.append({'name':name,'source':source_at(image,base,address,reg)})
    return {'records':records,'runtime_global_values_recovered':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit(image,base),indent=2))


if __name__=='__main__':main()
