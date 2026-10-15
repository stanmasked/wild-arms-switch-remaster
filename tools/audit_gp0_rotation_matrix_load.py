#!/usr/bin/env python3
"""Verify original GTE rotation matrix load before MVMVA; static evidence only."""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

CALL = 0x80077988
LOADER = 0x800B6DD8
NEXT_CALL = 0x800779C8

def word_at(image, base, address):
    if address < base or address+4 > base+len(image) or (address-base)%4:
        return None
    return struct.unpack_from('<I', image, address-base)[0]

def jal_target(word, pc):
    if word is None or word>>26 != 3: return None
    return ((pc+4)&0xf0000000)|((word&0x3ffffff)<<2)

def decode_lw(word):
    if word is None or word>>26 != 35: return None
    off=word&65535
    return ((word>>16)&31,(word>>21)&31,off-65536 if off>=32768 else off)

def decode_ctc2(word):
    if word is None or word>>26 != 18 or (word>>21)&31 != 6: return None
    return ((word>>16)&31,(word>>11)&31)

def decode_stack_a0(word):
    if word is None or word>>26 not in (8,9) or (word>>21)&31 != 29 or (word>>16)&31 != 4:
        return None
    off=word&65535
    return off-65536 if off>=32768 else off

def audit(image,base,call=CALL,loader=LOADER,next_call=NEXT_CALL):
    loading=[]
    for i in range(5):
        lw_addr=loader+4*i
        ctc_addr=loader+20+4*i
        lw=decode_lw(word_at(image,base,lw_addr))
        ctc=decode_ctc2(word_at(image,base,ctc_addr))
        loading.append({'lw':f'0x{lw_addr:08X}','ctc2':f'0x{ctc_addr:08X}',
                        'word_offset':4*i,'control_register':i,
                        'matched':lw==(8+i,4,i*4) and ctc==(8+i,i)})
    return {'loader':f'0x{loader:08X}','call':f'0x{call:08X}',
            'loader_called':jal_target(word_at(image,base,call),call)==loader,
            'delay_slot_a0_stack_offset':decode_stack_a0(word_at(image,base,call+4)),
            'five_rotation_control_words':all(x['matched'] for x in loading),
            'matrix_control_stores':loading,
            'downstream_mvmva_helper_call':
                jal_target(word_at(image,base,next_call),next_call)==0x800B68E8,
            'runtime_matrix_coefficients_recovered':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit(image,base),indent=2))

if __name__=='__main__': main()
