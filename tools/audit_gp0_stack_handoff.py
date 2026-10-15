#!/usr/bin/env python3
"""Static proof of stack+32 reuse across two MIPS calls, not memory contents."""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

SETUP_FUNCTION=0x8007790C
RENDER_FUNCTION=0x80077D08

def jal_target(word,pc):
    if word>>26!=3:return None
    return ((pc+4)&0xf0000000)|((word&0x03ffffff)<<2)

def addiu_from_sp(word):
    if word>>26 not in (8,9) or (word>>21)&31!=29:return None
    imm=word&65535
    return ((word>>16)&31,imm-65536 if imm>=32768 else imm)

def move_register(word):
    if word>>26 or (word&63)!=33 or ((word>>6)&31):return None
    dst,rs,rt=(word>>11)&31,(word>>21)&31,(word>>16)&31
    if not rs and rt:return dst,rt
    if not rt and rs:return dst,rs
    return None

def word_at(image,base,pc):
    if pc<base or pc+4>base+len(image) or (pc-base)%4:return None
    return struct.unpack_from('<I',image,pc-base)[0]

def scan(image,base,setup=SETUP_FUNCTION,render=RENDER_FUNCTION,window=32):
    if len(image)%4:raise ValueError('image must be word aligned')
    found=[]
    for pc in range(base,base+len(image)-4,4):
        if jal_target(word_at(image,base,pc),pc)!=setup:continue
        prep=None
        for prior in range(max(base,pc-window*4),pc,4):
            dec=addiu_from_sp(word_at(image,base,prior))
            mv=move_register(word_at(image,base,prior))
            if dec and dec[0]==6:
                prep={'address':f'0x{prior:08X}','stack_offset':dec[1]}
            if mv and mv[0]==6:
                for producer in range(max(base,pc-window*4),prior,4):
                    source=addiu_from_sp(word_at(image,base,producer))
                    if source and source[0]==mv[1]:
                        prep={'address':f'0x{producer:08X}','via_register':mv[1],
                              'move_address':f'0x{prior:08X}','stack_offset':source[1]}
        if prep is None:continue
        render_call=None
        for later in range(pc+8,min(base+len(image)-4,pc+window*4),4):
            if jal_target(word_at(image,base,later),later)!=render:continue
            if move_register(word_at(image,base,later+4))==(7,16):
                source16=None
                for before in range(max(base,pc-window*4),later,4):
                    dec=addiu_from_sp(word_at(image,base,before))
                    if dec and dec[0]==16:
                        source16={'address':f'0x{before:08X}','stack_offset':dec[1]}
                if source16:
                    render_call={'jal':f'0x{later:08X}',
                                 'delay_slot':f'0x{later+4:08X}','a3_source':source16}
            break
        found.append({'setup_jal':f'0x{pc:08X}','a2_source':prep,'render_call':render_call,
                      'same_stack_offset':bool(render_call and
                          prep['stack_offset']==render_call['a3_source']['stack_offset'])})
    return {'handoffs':found,'matched_same_stack_offset':sum(v['same_stack_offset'] for v in found),
            'contents_recovered':False}

def analyze_helper(image,base,helper=SETUP_FUNCTION):
    m=word_at(image,base,helper+0x18)
    n=word_at(image,base,helper+0xb4)
    c=word_at(image,base,helper+0xbc)
    target=jal_target(c,helper+0xbc) if c is not None else None
    return {'function':f'0x{helper:08X}',
            'a2_saved_to_s3':move_register(m)==(19,6) if m is not None else False,
            's3_to_a1_before_nested_call':move_register(n)==(5,19) if n is not None else False,
            'nested_call':f'0x{target:08X}' if target is not None else None}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps({'call_chain':scan(image,base),'helper':analyze_helper(image,base)},indent=2))

if __name__=='__main__':main()
