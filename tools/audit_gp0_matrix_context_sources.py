#!/usr/bin/env python3
"""May-source propagation on context-labelled MIPS CFG, with HI/LO provenance.

The graph is restricted: unsupported transfers terminate. No original game
bytes, arithmetic results or table samples appear in output.
"""
import argparse
import json
import struct
from collections import deque
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from .audit_gp0_trig_table import TABLE_LOAD_PCS
    from .audit_gp0_matrix_context_cfg import trace as context_trace
    from .audit_gp0_matrix_cfg_join import transfer
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from audit_gp0_trig_table import TABLE_LOAD_PCS
    from audit_gp0_matrix_context_cfg import trace as context_trace
    from audit_gp0_matrix_cfg_join import transfer


def pc_of(label):
    return int(label.split('@', 1)[0], 16)


def analyze(image, base, start=BUILDER, end=RETURN, lookups=TABLE_LOAD_PCS):
    graph = context_trace(image, base, start, end)
    if not graph['valid_range']:
        return {'valid_range': False, 'candidate_stores': []}
    outgoing = {}
    incoming = {}
    for edge in graph['edges']:
        a, b = edge['from'], edge['to']
        outgoing.setdefault(a, set()).add(b)
        incoming.setdefault(b, set()).add(a)
    entry=f'0x{start:08X}'
    empty=tuple(frozenset() for _ in range(34))
    states={entry: empty}
    outputs={}
    queue=deque([entry])
    queued={entry}
    while queue:
        node=queue.popleft()
        queued.discard(node)
        pc=pc_of(node)
        word=struct.unpack_from('<I', image, pc-base)[0]
        next_state=transfer(word, pc, states[node], lookups)
        if outputs.get(node)==next_state:
            continue
        outputs[node]=next_state
        for dst in sorted(outgoing.get(node, ())):
            # Recompute from each predecessor's current OUT state. Merely
            # unioning into the old IN state retains obsolete provenance
            # when a register write kills a source on a CFG loop.
            predecessors=[outputs[p] for p in incoming[dst] if p in outputs]
            combined=tuple(frozenset().union(*(v[i] for v in predecessors))
                           for i in range(34))
            if dst==entry:
                combined=tuple(a|b for a,b in zip(combined,empty))
            if states.get(dst)!=combined:
                states[dst]=combined
                if dst not in queued:
                    queue.append(dst)
                    queued.add(dst)
    stores=[]
    for node in sorted(states):
        pc=pc_of(node)
        word=struct.unpack_from('<I', image, pc-base)[0]
        off=word&65535
        if off&32768:
            off-=65536
        if (word>>26)==41 and ((word>>21)&31)==5 and off in range(0,18,2):
            reg=(word>>16)&31
            stores.append({'context':node,'offset':off,
                           'candidate_lookup_sources':sorted(states[node][reg]),
                           'merged_predecessors':len(incoming.get(node,()))>1})
    return {'valid_range': True,'candidate_stores':stores,
            'reachable_contexts':len(states),
            'unresolved_transfers':graph['unresolved'],
            'hi_lo_provenance':True,'full_mips_semantics':False,
            'assets_emitted':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(analyze(image,base),indent=2))


if __name__=='__main__':
    main()
