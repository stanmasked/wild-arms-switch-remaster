#!/usr/bin/env python3
"""Context-sensitive instruction edges for a restricted MIPS branch subset.

A delay-slot context is unique to its controlling branch PC. Unsupported
control transfers are terminal. Does not export executable or asset bytes.
"""
import argparse
import json
import struct
from collections import deque
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from .audit_gp0_matrix_cfg import direct_successors
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from audit_gp0_matrix_cfg import direct_successors


def trace(image, base, start=BUILDER, end=RETURN):
    if start < base or end < start or (start-base)%4 or (end-base)%4 or end+4 > base+len(image):
        return {'valid_range':False,'edges':[],'unresolved':[]}
    words={pc:struct.unpack_from('<I', image, pc-base)[0]
           for pc in range(start,end+4,4)}
    # Node: (pc, controlling branch or None). A delay-slot node is not the
    # same state as normal arrival at the identical instruction address.
    entry=(start,None)
    todo=deque([entry])
    visited=set()
    edges=set()
    unresolved=set()
    while todo:
        node=todo.popleft()
        if node in visited:
            continue
        visited.add(node)
        pc, controller=node
        kind, targets, delayed=direct_successors(words[pc],pc)
        if controller is not None:
            if delayed or kind=='unrecognized_special':
                unresolved.add((pc,'control_in_delay_slot'))
                continue
            parent_kind,parent_targets,_=direct_successors(words[controller],controller)
            if parent_kind == 'branch_likely':
                imm=words[controller]&65535
                imm=imm-65536 if imm&32768 else imm
                next_nodes=[((controller+4+(imm<<2))&0xffffffff,None)]
            else:
                next_nodes=[(target,None) for target in parent_targets] if parent_kind in ('conditional','jump') else []
        elif delayed:
            if kind == 'branch_likely':
                # Taken: execute the delay slot. Not taken: annul it.
                next_nodes=[(pc+4,pc),(pc+8,None)]
            elif kind in ('unsupported_regimm','call','indirect'):
                unresolved.add((pc,kind+'_requires_semantics'))
                continue
            next_nodes=[(pc+4,pc)]
        elif kind=='unrecognized_special':
            unresolved.add((pc,'malformed_jump_encoding'))
            continue
        else:
            next_nodes=[(pc+4,None)]
        for dest in next_nodes:
            if dest[0] not in words:
                unresolved.add((pc,'successor_outside_range'))
                continue
            edges.add((node,dest))
            if dest not in visited:
                todo.append(dest)
    def label(node):
        pc,parent=node
        return f'0x{pc:08X}' if parent is None else f'0x{pc:08X}@delay_of_0x{parent:08X}'
    return {'valid_range':True,
            'edges':[{'from':label(a),'to':label(b)} for a,b in sorted(edges)],
            'unresolved':[{'pc':f'0x{pc:08X}','reason':reason} for pc,reason in sorted(unresolved)],
            'reachable_contexts':len(visited), 'complete_mips_semantics':False,
            'assets_emitted':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path)
    args=p.parse_args()
    base,image=parse_exe(args.exe.read_bytes())
    print(json.dumps(trace(image,base),indent=2))


if __name__=='__main__':
    main()
