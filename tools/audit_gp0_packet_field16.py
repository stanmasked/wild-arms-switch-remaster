#!/usr/bin/env python3
"""Find narrowly proven pointer arithmetic feeding polygon-structure field +16.

Static local MIPS pattern evidence only; no original bytes are emitted.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_gp0_callers import audit_callers
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_gp0_callers import audit_callers
    from audit_original_nclip_winding import parse_exe


def instruction(word):
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    imm = word & 65535
    imm = imm - 65536 if imm >= 32768 else imm
    if op in (35, 43):
        return ('LW' if op == 35 else 'SW', rs, rt, imm)
    if op == 0 and (word & 63) in (0x21, 0x20) and ((word >> 6) & 31) == 0:
        return ('ADDU' if (word & 63) == 0x21 else 'ADD', rs, rt, rd)
    return None


def pointer_field_stores(image, base, structure_registers=(16,17), lookback=20):
    """Require SW field16 <- ADDU(LW field0, LW cursor[0|4]).

    Cursor must be loaded from structure field12. Limited linear scan,
    not flow-sensitive or alias-aware.
    """
    words = list(struct.unpack(f'<{len(image)//4}I', image))
    ins = [instruction(w) for w in words]
    output=[]
    for i,store in enumerate(ins):
        if not store or store[0]!='SW' or store[1] not in structure_registers or store[3]!=16:
            continue
        base_reg, dest = store[1], store[2]
        start=max(0,i-lookback)
        for j in range(i-1,start-1,-1):
            addu=ins[j]
            if not addu or addu[0]!='ADDU' or addu[3]!=dest:
                continue
            lhs,rhs=addu[1:3]
            if lhs==rhs: continue
            field0=None; cursor_data=None; cursor_load=None
            for k in range(j-1,start-1,-1):
                instr=ins[k]
                if not instr or instr[0]!='LW': continue
                if instr[1]==base_reg and instr[2] in (lhs,rhs) and instr[3]==0:
                    field0=field0 or (k,instr[2])
                if instr[2] in (lhs,rhs) and instr[3] in (0,4):
                    for m in range(k-1,start-1,-1):
                        src=ins[m]
                        if src and src==('LW',base_reg,instr[1],12):
                            cursor_data=cursor_data or (k,instr[2],instr[3])
                            cursor_load=cursor_load or m
                            break
            if not field0 or not cursor_data or field0[1]==cursor_data[1]:continue
            if {field0[1],cursor_data[1]}!={lhs,rhs}:continue
            output.append({
                'store':f'0x{base+4*i:08X}', 'structure_register':base_reg,
                'source_cursor_field_offset':12,
                'base_pointer_field_offset':0,
                'result_field_offset':16,
                'cursor_word_offset':cursor_data[2],
                'cursor_load':f'0x{base+4*cursor_load:08X}',
                'offset_word_load':f'0x{base+4*cursor_data[0]:08X}',
                'base_pointer_load':f'0x{base+4*field0[0]:08X}',
                'address_add':f'0x{base+4*j:08X}'
            })
            break
    return output


def audit(image,base):
    calls=audit_callers(image,base)
    stores=pointer_field_stores(image,base)
    matched=[]
    for record in calls['records']:
        for call in record['direct_jal_callers']:
            a0=call.get('last_a0_write')
            if not a0 or a0.get('kind')!='LW' or a0.get('offset')!=16:continue
            matching=[s for s in stores if s['structure_register']==a0['base_register']]
            matched.append({'call':call['call'],'handler_nclip':record['nclip'],
                            'structure_register':a0['base_register'],
                            'matching_field16_store_candidates':matching})
    return {'pattern_matches':len(stores),'stores':stores,
            'direct_calls_using_structure_field16':len(matched),
            'call_site_contexts':matched,
            'runtime_address_or_packet_contents_recovered':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(audit(image,base),indent=2))


if __name__=='__main__':main()
