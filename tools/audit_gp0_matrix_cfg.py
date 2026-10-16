#!/usr/bin/env python3
"""Build a conservative direct-branch CFG for the original MIPS matrix builder.

Branch delay slots are explicit nodes. Indirect jumps and external calls are
reported as unresolved. No original executable bytes are included in output.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN


def signed16(value):
    return value - 65536 if value & 0x8000 else value


def direct_successors(word, pc):
    """Return (kind, targets after delay slot, has_delay_slot)."""
    op = word >> 26
    rt = (word >> 16) & 31
    fn = word & 63
    if op in (4, 5, 6, 7) or (op == 1 and rt in (0, 1, 16, 17)):
        target = (pc + 4 + (signed16(word & 65535) << 2)) & 0xffffffff
        return 'conditional', (target, pc + 8), True
    if op == 1:
        return 'unsupported_regimm', (), True
    if op in (2, 3):
        target = ((pc + 4) & 0xf0000000) | ((word & 0x03ffffff) << 2)
        return ('call' if op == 3 else 'jump'), (target,), True
    if op == 0 and fn in (8, 9):
        return 'indirect', (), True
    if op in (20, 21, 22, 23):
        return 'branch_likely', (), True
    return 'linear', (pc + 4,), False


def analyze(image, base, start=BUILDER, end=RETURN):
    if start < base or end < start or (start-base) % 4 or (end-base) % 4 or end + 4 > base + len(image):
        return {'valid_range': False, 'edges': [], 'unresolved': []}
    words = {pc: struct.unpack_from('<I', image, pc-base)[0]
             for pc in range(start, end+4, 4)}
    edges = []
    unresolved = []
    delay_slots = {pc+4 for pc, word in words.items()
                   if direct_successors(word, pc)[2] and pc+4 <= end}
    for pc, word in words.items():
        kind, targets, delayed = direct_successors(word, pc)
        if kind == 'linear':
            if pc not in delay_slots and pc + 4 <= end:
                edges.append({'from': f'0x{pc:08X}', 'to': f'0x{pc+4:08X}', 'kind': kind})
            continue
        slot = pc + 4
        if slot > end:
            unresolved.append({'pc': f'0x{pc:08X}', 'reason': 'delay_slot_out_of_range'})
            continue
        edges.append({'from': f'0x{pc:08X}', 'to': f'0x{slot:08X}', 'kind': 'delay_slot'})
        if kind in ('indirect', 'branch_likely', 'call', 'unsupported_regimm'):
            unresolved.append({'pc': f'0x{pc:08X}', 'reason': kind + '_requires_semantics'})
            continue
        for target in targets:
            if start <= target <= end and target % 4 == 0:
                edges.append({'from': f'0x{slot:08X}', 'to': f'0x{target:08X}',
                              'kind': kind, 'via': f'0x{pc:08X}'})
            else:
                unresolved.append({'pc': f'0x{pc:08X}', 'reason': 'target_outside_range'})
    return {'valid_range': True, 'edges': edges, 'unresolved': unresolved,
            'control_flow_complete': False, 'assets_emitted': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path)
    a = p.parse_args()
    base, image = parse_exe(a.exe.read_bytes())
    print(json.dumps(analyze(image, base), indent=2))


if __name__ == '__main__':
    main()
