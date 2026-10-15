#!/usr/bin/env python3
"""Conservative straight-line register provenance within the PS1 matrix builder.

Branch boundaries reset provenance: no inter-block or delay-slot claims.
Never prints original game bytes or lookup values.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from .audit_gp0_trig_table import TABLE_LOAD_PCS
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from audit_gp0_trig_table import TABLE_LOAD_PCS


def trace(image, base, start=BUILDER, end=RETURN, lookup_pcs=TABLE_LOAD_PCS):
    if start < base or end < start or (start-base) % 4 or (end-base) % 4 or end+4 > base+len(image):
        return {'valid_range': False, 'candidate_stores': []}
    # Register provenance is a *within-basic-block* under-approximation.
    regs = [set() for _ in range(32)]
    lo = set()
    hi = set()
    stores = []
    branch_delay = False
    reset_after_delay = False
    for pc in range(start, end+4, 4):
        if reset_after_delay:
            regs = [set() for _ in range(32)]
            lo = set()
            hi = set()
            reset_after_delay = False
        word = struct.unpack_from('<I', image, pc-base)[0]
        op = word >> 26
        rs, rt, rd, sa, fn = ((word>>21)&31, (word>>16)&31,
                              (word>>11)&31, (word>>6)&31, word&63)
        if op == 0x29 and rs == 5 and 0 <= ((word&65535)^0x8000)-0x8000 < 18:
            offset = ((word&65535)^0x8000)-0x8000
            stores.append({'pc': f'0x{pc:08X}', 'offset': offset,
                           'candidate_lookup_sources': sorted(regs[rt]),
                           'proven_across_branches': False})
        writes = None
        source = set()
        if pc in lookup_pcs and op == 35:
            writes, source = rt, {f'0x{pc:08X}'}
        elif op in (32,33,35,36,37, 15):  # Loads or LUI overwrite destination.
            writes = rt
        elif op in (8,9,10,11,12,13,14):
            writes, source = rt, set(regs[rs])
        elif op == 0:
            if fn in (24,25):
                lo = set(regs[rs]) | set(regs[rt])
                hi = set(lo)
            elif fn in (16,18) and rs == 0 and rt == 0:
                writes, source = rd, set(hi if fn == 16 else lo)
            elif fn in (0,2,3):
                writes, source = rd, set(regs[rt])
            elif fn in (4,6,7,33,35,36,37,38,39,42,43):
                writes, source = rd, set(regs[rs]) | set(regs[rt])
        if writes is not None and writes != 0:
            regs[writes] = source
        # All control transfers terminate a block after their delay slot.
        control = (op in (2,3,4,5,6,7,1) or
                   (op == 0 and fn in (8,9)) or op in (20,21,22,23))
        if branch_delay:
            reset_after_delay = True
            branch_delay = False
        if control:
            branch_delay = True
    return {'valid_range': True, 'candidate_stores': stores,
            'analysis': 'straight_line_only_resets_after_branch_delay',
            'full_control_flow_proven': False, 'assets_emitted': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path)
    args = p.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(trace(image, base), indent=2))


if __name__ == '__main__':
    main()
