#!/usr/bin/env python3
"""Audit direct global SW stores and the MIPS JAL delay-slot a3 pointer.

Conservative statically matched instructions, not a complete alias/CFG analysis.
Input must be a locally extracted PS-X EXE; no original game content is emitted.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_original_nclip_winding import parse_exe

GLOBALS = (0x800D2C3C, 0x800D2DB8)
RENDER_CALL = 0x80077D08

def direct_global_stores(image, base, targets=GLOBALS, window=12):
    """Only LUI base + direct SW [base+signed16] pairs; no alias claims."""
    words = struct.unpack(f'<{len(image)//4}I', image)
    found = []
    for i, word in enumerate(words):
        if word >> 26 != 43:
            continue
        rs, rt, imm = (word >> 21) & 31, (word >> 16) & 31, word & 65535
        signed_imm = imm-65536 if imm >= 32768 else imm
        for j in range(max(0,i-window),i):
            prev = words[j]
            if prev >> 26 != 15 or ((prev >> 16) & 31) != rs:
                continue
            address = (((prev & 65535) << 16) + signed_imm) & 0xffffffff
            if address in targets:
                found.append({'global_address':f'0x{address:08X}',
                              'store':f'0x{base+4*i:08X}',
                              'lui':f'0x{base+4*j:08X}',
                              'source_register':rt})
                break
    return found

def delay_slot_a3_sources(image,base,target=RENDER_CALL,lookback=16):
    words=struct.unpack(f'<{len(image)//4}I',image)
    found=[]
    for i,w in enumerate(words[:-1]):
        pc=base+4*i
        if w>>26 != 3 or (((pc+4)&0xf0000000)|((w&0x3ffffff)<<2)) != target:
            continue
        delay=words[i+1]
        rsource=None
        if delay>>26 == 0 and (delay&63)==33 and ((delay>>6)&31)==0 and (delay>>11)&31==7:
            rs,rt=(delay>>21)&31,(delay>>16)&31
            if rs == 0 and rt: rsource=rt
            elif rt == 0 and rs: rsource=rs
        provenance=None
        if rsource is not None:
            for j in range(i-1,max(-1,i-lookback-1),-1):
                prev=words[j]
                if prev>>26 not in (8,9):continue
                if (prev>>16)&31 != rsource or (prev>>21)&31 != 29:continue
                imm=prev&65535
                provenance={'instruction':f'0x{base+4*j:08X}',
                            'operation':'ADDI' if prev>>26==8 else 'ADDIU',
                            'base_register':'sp',
                            'signed_offset':imm-65536 if imm>=32768 else imm}
                break
        found.append({'jal':f'0x{pc:08X}',
                      'delay_slot':f'0x{pc+4:08X}',
                      'a3_source_register':rsource,
                      'source_from_sp':provenance})
    return found

def audit(image,base):
    stores=direct_global_stores(image,base)
    calls=delay_slot_a3_sources(image,base)
    return {'global_targets':[f'0x{t:08X}' for t in GLOBALS],
            'direct_global_sw_candidates':stores,
            'a3_delay_slot_calls':calls,
            'indirect_global_writes_excluded':True,
            'runtime_pointer_values_known':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit(image,base),indent=2))

if __name__=='__main__':main()
