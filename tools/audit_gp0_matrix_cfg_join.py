#!/usr/bin/env python3
"""Conservative may-source propagation over supported MIPS CFG edges.

Unsupported writes kill destination provenance. Calls/indirect jumps terminate
paths. Output contains source PCs, never original opcode words or game assets.
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
    from .audit_gp0_matrix_cfg import analyze as cfg_analyze
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from audit_gp0_trig_table import TABLE_LOAD_PCS
    from audit_gp0_matrix_cfg import analyze as cfg_analyze


def transfer(word, pc, state, lookups):
    regs = [set(v) for v in state]
    op, rs, rt, rd, fn = word>>26, (word>>21)&31, (word>>16)&31, (word>>11)&31, word&63
    out = None
    val = set()
    if op in (32,33,35,36,37,15):
        out = rt
        if op == 35 and pc in lookups:
            val = {f'0x{pc:08X}'}
    elif op in (16,17,18,19) and rs in (0,2):
        # MFCn/CFCn overwrite a GPR with coprocessor data. No proven
        # source from the previous GPR value survives the transfer.
        out, val = rt, set()
    elif op in (8,9,10,11,12,13,14):
        out, val = rt, set(regs[rs])
    elif op == 0:
        if fn in (24,25) and rd == 0 and ((word>>6)&31) == 0:
            product_sources = set(regs[rs]) | set(regs[rt])
            regs[32] = set(product_sources)  # HI
            regs[33] = set(product_sources)  # LO
        elif fn in (17,19) and rt == 0 and rd == 0 and ((word>>6)&31) == 0:
            regs[32 if fn == 17 else 33] = set(regs[rs])
        elif fn in (0,2,3):
            out, val = rd, set(regs[rt])
        elif fn in (4,6,7,32,33,34,35,36,37,38,39,42,43):
            out, val = rd, set(regs[rs]) | set(regs[rt])
        elif fn in (16,18) and rs == 0 and rt == 0 and ((word>>6)&31) == 0:
            out, val = rd, set(regs[32 if fn == 16 else 33])
        elif fn == 9:
            out = rd # JALR link value
    elif op == 3:
        out = 31
    if out is not None and out != 0:
        regs[out] = val
    regs[0] = set()
    return tuple(frozenset(v) for v in regs)


def analyze(image, base, start=BUILDER, end=RETURN, lookups=TABLE_LOAD_PCS):
    cfg = cfg_analyze(image, base, start, end)
    if not cfg['valid_range']:
        return {'valid_range': False, 'candidate_stores': []}
    edges = {}
    incoming = {}
    for edge in cfg['edges']:
        a, b = int(edge['from'],16), int(edge['to'],16)
        edges.setdefault(a,set()).add(b)
        incoming.setdefault(b,set()).add(a)
    zero = tuple(frozenset() for _ in range(34))
    states = {start: zero}
    outputs = {}
    queue = deque([start])
    queued = {start}
    while queue:
        pc = queue.popleft()
        queued.discard(pc)
        word = struct.unpack_from('<I', image, pc-base)[0]
        after = transfer(word, pc, states[pc], lookups)
        if outputs.get(pc) == after:
            continue
        outputs[pc] = after
        for dst in sorted(edges.get(pc, ())):
            predecessors = [outputs[p] for p in incoming[dst] if p in outputs]
            combined = tuple(frozenset().union(*(v[i] for v in predecessors))
                             for i in range(34))
            if states.get(dst) != combined:
                states[dst] = combined
                if dst not in queued:
                    queue.append(dst)
                    queued.add(dst)
    stores = []
    for pc in sorted(states):
        word = struct.unpack_from('<I',image,pc-base)[0]
        offset = (word&65535)
        offset = offset-65536 if offset&32768 else offset
        if word>>26 == 41 and ((word>>21)&31) == 5 and offset in range(0,18,2):
            reg=(word>>16)&31
            stores.append({'pc':f'0x{pc:08X}','offset':offset,
                           'candidate_lookup_sources':sorted(states[pc][reg]),
                           'paths_merged':len(incoming.get(pc,set()))>1})
    return {'valid_range':True,'candidate_stores':stores,
            'reachable_instructions':len(states),
            'unresolved_transfers':cfg['unresolved'],
            'full_control_flow_proven':False,
            'hi_lo_tracking':True,'assets_emitted':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    a=p.parse_args()
    base,image=parse_exe(a.exe.read_bytes())
    print(json.dumps(analyze(image,base),indent=2))


if __name__=='__main__':
    main()
