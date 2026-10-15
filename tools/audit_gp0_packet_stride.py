#!/usr/bin/env python3
"""Recover GPU packet argument alias and per-record increment near NCLIP."""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_gp0_triangle_layouts import inspect_layouts
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_gp0_triangle_layouts import inspect_layouts
    from audit_original_nclip_winding import parse_exe

def decode_packet_alias(word):
    # addu r11,r4,r0 or addu r11,r0,r4
    if word >> 26 or (word & 63) != 0x21 or ((word >> 6) & 31):
        return False
    return ((word >> 11) & 31) == 11 and {
        (word >> 21) & 31, (word >> 16) & 31} == {0,4}

def decode_advance(word):
    # ADDI and ADDIU a0,a0,positive immediate are both valid.
    if (word >> 26) not in (8,9) or ((word >> 21) & 31) != 4 or ((word >> 16) & 31) != 4:
        return None
    imm=word & 0xffff
    return imm if 0 < imm < 0x8000 else None

def inspect_stride(image,base,nclip,lookback=48):
    if nclip < base or nclip >= base + len(image) or (nclip-base)%4:
        return None
    start=max(base,nclip-4*lookback)
    words=[struct.unpack_from('<I',image,addr-base)[0] for addr in range(start,nclip,4)]
    aliases=[i for i,w in enumerate(words) if decode_packet_alias(w)]
    if not aliases:
        return None
    i=aliases[-1]
    increments=[(j,decode_advance(w)) for j,w in enumerate(words[i+1:],i+1)]
    increments=[(j,imm) for j,imm in increments if imm is not None]
    if not increments:
        return None
    j,stride=increments[0]
    return {'alias_address':f'0x{start+4*i:08X}',
            'advance_address':f'0x{start+4*j:08X}',
            'source_cpu_register':'a0','packet_cpu_register':'r11',
            'stride_bytes':stride}

def audit_packet_stride(image,base):
    report=inspect_layouts(image,base)
    for site in report['sites']:
        site['packet_pointer']=inspect_stride(image,base,int(site['nclip'],16)) if site.get('ot_packet') else None
        if site['packet_pointer'] and site.get('ot_packet'):
            site['packet_pointer']['gpu_words_after_tag']=site['ot_packet']['packet_words']
    return {'nclip_sites':report['nclip_count'],
            'ot_packet_candidates':report['ot_packet_candidates'],
            'packet_pointer_matches':sum(bool(s['packet_pointer']) for s in report['sites']),
            'sites':report['sites']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path)
    args=parser.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit_packet_stride(image,base),indent=2))

if __name__=='__main__':
    main()
