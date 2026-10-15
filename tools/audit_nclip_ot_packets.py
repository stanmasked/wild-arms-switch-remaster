#!/usr/bin/env python3
"""Static NCLIP-positive path audit: PS1 GPU packet header and OT linking."""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_nclip_polygon_writes import describe
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_nclip_polygon_writes import describe
    from audit_original_nclip_winding import parse_exe

def fields(word):
    return word >> 26, (word >> 21)&31, (word >> 16)&31, word & 65535

def recognize(words, addresses):
    avsz=next((i for i,w in enumerate(words) if w&0xfe00003f==0x4a00002d),None)
    if avsz is None: return None
    for i in range(avsz+1,len(words)-7):
        opcode,slot,old,offset=fields(words[i])
        if (opcode,offset)!=(35,0) or old==0: continue
        op1,_,maskreg,imm1=fields(words[i+1])
        op2,src2,dst2,imm2=fields(words[i+2])
        if (op1,imm1)!=(15,255) or op2!=13 or src2!=maskreg or dst2!=maskreg or imm2!=65535: continue
        w3=words[i+3]
        if w3>>26 or w3&63!=36: continue
        a,b,d=(w3>>21)&31,(w3>>16)&31,(w3>>11)&31
        if maskreg not in (a,b): continue
        packet=b if a==maskreg else a
        if packet==0 or d!=packet: continue
        op4,_,sizereg,szimm=fields(words[i+4])
        w5=words[i+5]
        if op4!=15 or not 1<=szimm>>8<=255 or szimm&255: continue
        if w5>>26 or w5&63!=37: continue
        aa,bb,dd=(w5>>21)&31,(w5>>16)&31,(w5>>11)&31
        if sizereg not in (aa,bb): continue
        if (bb if aa==sizereg else aa)!=old or dd!=old: continue
        if fields(words[i+6])!=(43,packet,old,0): continue
        if fields(words[i+7])!=(43,slot,packet,0): continue
        return {'avsz3':f'0x{addresses[avsz]:08X}',
                'ot_old_head_load':f'0x{addresses[i]:08X}',
                'packet_header_store':f'0x{addresses[i+6]:08X}',
                'ot_head_store':f'0x{addresses[i+7]:08X}',
                'packet_words':szimm>>8,
                'packet_base_register':packet,
                'ot_slot_register':slot}
    return None

def audit(image,base):
    report=describe(image,base)
    for site in report['sites']:
        site['ot_packet']=None
        if not site['blez']: continue
        start=int(site['blez'],16)+8
        stop=int(site['branch_target'],16)
        if stop<=start or stop>base+len(image): continue
        addresses=list(range(start,stop,4))
        words=[struct.unpack_from('<I',image,addr-base)[0] for addr in addresses]
        site['ot_packet']=recognize(words,addresses)
    return {'nclip_count':report['nclip_count'],
            'mac0_blez_count':report['mac0_blez_count'],
            'sxy_triplet_count':report['mac0_blez_with_sxy_triplet'],
            'ot_packet_candidates':sum(bool(s['ot_packet']) for s in report['sites']),
            'sites':report['sites']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path)
    args=parser.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit(image,base),indent=2))

if __name__=='__main__': main()
