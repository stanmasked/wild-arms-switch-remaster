#!/usr/bin/env python3
"""Conservative direct JAL caller and a0 input-source audit for packet routines.

Only static direct JAL calls and the nearest textual preceding a0 write are
reported. Input is a privately extracted PS-X EXE; no game bytes emitted.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_gp0_packet_stride import audit_packet_stride
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_gp0_packet_stride import audit_packet_stride
    from audit_original_nclip_winding import parse_exe


def jal_target(word, pc):
    if word >> 26 != 3:
        return None
    return ((pc + 4) & 0xf0000000) | ((word & 0x03ffffff) << 2)


def a0_definition(word):
    op, rs, rt, imm = word >> 26, (word >> 21) & 31, (word >> 16) & 31, word & 65535
    if rt == 4 and op in (35, 33, 37, 36):
        return {'kind': {35:'LW',33:'LH',37:'LHU',36:'LBU'}[op],
                'base_register': rs, 'offset': imm if imm < 32768 else imm-65536}
    if rt == 4 and op in (8, 9, 12, 13, 15):
        return {'kind': {8:'ADDI',9:'ADDIU',12:'ANDI',13:'ORI',15:'LUI'}[op],
                'base_register': rs,
                'immediate': (imm-65536 if imm >= 32768 else imm) if op in (8,9) else imm}
    if op == 0 and ((word >> 11) & 31) == 4 and (word & 63) in (0x21,0x23):
        return {'kind':'ADDU' if (word & 63)==0x21 else 'SUBU',
                'source_registers':[rs,rt]}
    return None


def direct_calls(image, base):
    result={}
    for offset in range(0,len(image)//4*4,4):
        pc=base+offset
        target=jal_target(struct.unpack_from('<I',image,offset)[0],pc)
        if target is not None:
            result.setdefault(target,[]).append(pc)
    return result


def find_nearby_a0(image,base,call,window=16):
    """Last textual a0 assignment in lookback; not a CFG proof."""
    start=max(base,call-window*4)
    latest=None
    for pc in range(start,call,4):
        definition=a0_definition(struct.unpack_from('<I',image,pc-base)[0])
        if definition is not None:
            latest={'address':f'0x{pc:08X}',**definition}
    return latest


def audit_callers(image,base,nearby_bytes=192):
    packets=audit_packet_stride(image,base)
    targets=direct_calls(image,base)
    records=[]
    for site in packets['sites']:
        if not site.get('packet_pointer'):
            continue
        nclip=int(site['nclip'],16)
        candidates=[(t,calls) for t,calls in targets.items()
                    if 0 <= nclip-t <= nearby_bytes]
        if candidates:
            target,calls=max(candidates,key=lambda pair:pair[0])
            calls=[{'call':f'0x{call:08X}',
                    'last_a0_write':find_nearby_a0(image,base,call)} for call in calls]
        else:
            target,calls=None,[]
        records.append({'nclip':site['nclip'],
                        'layout':(site.get('gp0_layout') or {}).get('layout_candidate'),
                        'stride_bytes':site['packet_pointer']['stride_bytes'],
                        'direct_jal_target_candidate':f'0x{target:08X}' if target is not None else None,
                        'direct_jal_callers':calls})
    return {'packet_paths':len(records),
            'paths_with_direct_jal_candidate':sum(bool(r['direct_jal_callers']) for r in records),
            'records':records,'runtime_pointer_contents_known':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit_callers(image,base),indent=2))


if __name__=='__main__':main()
