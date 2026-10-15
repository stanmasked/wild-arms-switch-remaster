#!/usr/bin/env python3
"""Static GP0 first-command-word write audit. No game asset bytes emitted."""
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

def decode_store(word):
    op=word>>26
    if op not in (0x28,0x29,0x2b): return None
    offset=word&65535
    if offset&32768: offset-=65536
    return {'operation':{0x28:'SB',0x29:'SH',0x2b:'SW'}[op],
            'base':(word>>21)&31,'source':(word>>16)&31,'offset':offset}

def decode_load(word):
    op=word>>26
    if op not in (0x20,0x24,0x23): return None
    offset=word&65535
    if offset&32768: offset-=65536
    return {'operation':{0x20:'LB',0x24:'LBU',0x23:'LW'}[op],
            'base':(word>>21)&31,'destination':(word>>16)&31,'offset':offset}

def trace_packet_first_word(image,base,branch,target,packet_register,lookback=24):
    """Inspect packet+4 command-word stores and packet+7 opcode-byte stores.

    LBU/SB pairing suggests opcode-byte preservation but cannot reveal its value.
    """
    start=max(base,branch-4*lookback)
    stop=min(base+len(image),target)
    if start>branch or stop<=branch: return []
    events=[]
    for address in range(start,stop,4):
        word=struct.unpack_from('<I',image,address-base)[0]
        store=decode_store(word)
        if not store or store['base']!=packet_register: continue
        if not ((store['operation']=='SW' and store['offset']==4) or
                (store['operation']=='SB' and store['offset']==7) or
                (store['operation']=='SH' and store['offset'] in (4,6))):
            continue
        source=store['source']
        preserved=False
        for previous in range(max(start,address-32),address,4):
            candidate=struct.unpack_from('<I',image,previous-base)[0]
            load=decode_load(candidate)
            if (load and load['operation']=='LBU' and
                    load['base']==packet_register and load['offset']==7 and
                    load['destination']==source and store['operation']=='SB'):
                preserved=True
        events.append({'address':f'0x{address:08X}',
                       'operation':store['operation'],
                       'byte_offset':store['offset'],
                       'source_cpu_register':source,
                       'phase':'before_blez' if address<branch else
                               'delay_slot' if address<branch+8 else 'fallthrough',
                       'lbu_opcode_byte_preservation':preserved})
    return events

def inspect_opcode_sources(image,base):
    report=inspect_layouts(image,base)
    counts={'first_word_stores':0,'opcode_byte_stores':0,'byte_preservations':0}
    for site in report['sites']:
        packet=site.get('ot_packet')
        site['gp0_first_word_events']=[]
        if not packet or not site['blez']: continue
        events=trace_packet_first_word(
            image,base,int(site['blez'],16),int(site['branch_target'],16),
            packet['packet_base_register'])
        site['gp0_first_word_events']=events
        counts['first_word_stores']+=sum(e['operation']=='SW' for e in events)
        counts['opcode_byte_stores']+=sum(
            e['operation']=='SB' and e['byte_offset']==7 for e in events)
        counts['byte_preservations']+=sum(e['lbu_opcode_byte_preservation'] for e in events)
    return {'layout_counts':report['counts_by_layout'],
            'opcode_bytes_decoded_from_runtime':0,
            'counts':counts,'sites':report['sites']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path)
    args=parser.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(inspect_opcode_sources(image,base),indent=2))

if __name__=='__main__': main()
