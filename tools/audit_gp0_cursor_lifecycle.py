#!/usr/bin/env python3
"""Audit direct initialization and advancement of polygon cursor at struct +12.

Bounded static instruction patterns only. Requires privately extracted PS-X EXE.
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
    rs, rt, rd = (word >> 21)&31, (word >> 16)&31, (word >> 11)&31
    imm = word & 65535
    if imm & 0x8000:
        imm -= 65536
    if op in (35,43):
        return ('LW' if op==35 else 'SW', rt, rs, imm)
    if op in (8,9):
        return ('ADDI' if op==8 else 'ADDIU', rt, rs, imm)
    return None


def lifecycle(image, base, region_start=None, region_stop=None):
    if len(image) % 4:
        raise ValueError('load image must be word aligned')
    start = base if region_start is None else region_start
    stop = base + len(image) if region_stop is None else region_stop
    if not (base <= start <= stop <= base+len(image)) or (start-base)%4 or (stop-base)%4:
        raise ValueError('invalid aligned scan range')
    words=struct.unpack(f'<{len(image)//4}I', image)
    decoded=[decode(w) for w in words]
    result=[]
    for addr in range(start,stop,4):
        index=(addr-base)//4
        store=decoded[index]
        if store is None or store[0]!='SW' or store[3]!=12 or store[2] not in (16,17):
            continue
        dest, structreg = store[1], store[2]
        # Find a nearby ADDIU/ADDI that defines exactly the stored register.
        lower=max((start-base)//4,index-5)
        for ai in range(index-1,lower-1,-1):
            a=decoded[ai]
            if a is None or a[0] not in ('ADDI','ADDIU') or a[1]!=dest:
                continue
            for li in range(ai-1,max((start-base)//4,ai-5)-1,-1):
                l=decoded[li]
                if l is None or l[0]!='LW' or l[1]!=a[2]:
                    continue
                if l[2]==structreg and l[3]==0 and a[3]==12:
                    kind='initialize_base_plus_12'
                elif l[2]==structreg and l[3]==12 and a[3]==4:
                    kind='advance_cursor_plus_4'
                else:
                    continue
                result.append({'store':f'0x{addr:08X}', 'kind':kind,
                               'structure_register':structreg,
                               'source_load':f'0x{base+li*4:08X}',
                               'increment':f'0x{base+ai*4:08X}',
                               'delta':a[3]})
                break
            else:
                continue
            break
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    p.add_argument('--region-start',type=lambda n:int(n,0),default=None)
    p.add_argument('--region-stop',type=lambda n:int(n,0),default=None)
    a=p.parse_args()
    base,image=parse_exe(a.exe.read_bytes())
    matches=lifecycle(image,base,a.region_start,a.region_stop)
    print(json.dumps({'matches':matches,'initializations':sum(m['kind']=='initialize_base_plus_12' for m in matches),'advances':sum(m['kind']=='advance_cursor_plus_4' for m in matches),'runtime_values_recovered':False},indent=2))

if __name__=='__main__':main()
