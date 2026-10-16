#!/usr/bin/env python3
"""Private PS-X EXE MIPS matrix preflight: aggregate counts, no game data output.

An optional exploratory replay uses synthetic zero registers, not gameplay
state. Never exposes executable words, table entries, registers or coefficients.
"""
import argparse
import json
import struct
from collections import Counter
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from .audit_gp0_trig_table import TABLE, ENTRIES
    from .mips_control_flow import execute, LOADS, STORES
    from .mips_matrix_memory import MappedMemory, MATRIX_OFFSETS, MATRIX_SIZE
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN
    from audit_gp0_trig_table import TABLE, ENTRIES
    from mips_control_flow import execute, LOADS, STORES
    from mips_matrix_memory import MappedMemory, MATRIX_OFFSETS, MATRIX_SIZE


def instruction_family(word):
    """Summarize encodings supported by the current partial integer executor."""
    op = word >> 26
    rs, rt, rd, sa, fn = ((word >> 21) & 31, (word >> 16) & 31,
                         (word >> 11) & 31, (word >> 6) & 31, word & 63)
    if word == 0:
        return 'nop', True
    if op == 0:
        if fn in (8, 9):
            return 'indirect_jump', rt == 0 and sa == 0 and (fn == 9 or rd == 0)
        if fn in (0, 2, 3):
            return 'shift', rs == 0
        if fn in (4, 6, 7):
            return 'variable_shift', sa == 0
        if fn in (24, 25):
            return 'multiply', rd == 0 and sa == 0
        if fn in (16, 18):
            return 'hi_lo_move', rs == 0 and rt == 0 and sa == 0
        if fn in (17, 19):
            return 'hi_lo_move', rt == 0 and rd == 0 and sa == 0
        if fn in (32, 33, 34, 35, 36, 37, 38, 39, 42, 43):
            return 'alu_register', sa == 0
        return 'unsupported_special', False
    if op in LOADS:
        return 'aligned_load', True
    if op in STORES:
        return 'aligned_store', True
    if op in (4, 5, 6, 7, 20, 21, 22, 23):
        return 'branch', True
    if op == 1:
        return 'regimm_branch', rt in (0, 1, 2, 3)
    if op in (2, 3):
        return 'jump', True
    if op in (8, 9, 10, 11, 12, 13, 14):
        return 'alu_immediate', True
    if op == 15:
        return 'lui', rs == 0
    if op in (16, 17, 18, 19):
        return 'coprocessor', False
    return 'unsupported_opcode', False


def analyze(blob, start=BUILDER, end=RETURN, *, table=TABLE,
            matrix_address=0x80110000, explore=False, max_steps=512,
            initial_registers=None):
    base, image = parse_exe(blob)
    if (start < base or end < start or end + 4 > base + len(image)
            or (start - base) % 4 or (end - base) % 4):
        return {'valid_range': False, 'assets_emitted': False}
    counts = Counter()
    unsupported = Counter()
    for pc in range(start, end + 4, 4):
        word, = struct.unpack_from('<I', image, pc - base)
        family, accepted = instruction_family(word)
        counts[family] += 1
        if not accepted:
            unsupported[family] += 1
    table_present = base <= table and table + ENTRIES * 4 <= base + len(image)
    result = {
        'valid_range': True,
        'builder_start': f'0x{start:08X}',
        'builder_end_inclusive': f'0x{end:08X}',
        'instruction_count': (end - start) // 4 + 1,
        'instruction_families': dict(sorted(counts.items())),
        'unsupported_families': dict(sorted(unsupported.items())),
        'static_supported_count': sum(counts.values()) - sum(unsupported.values()),
        'trig_table_mapped_in_image': table_present,
        'assets_emitted': False,
        'original_game_state_known': False,
        'bit_exact_original_coefficients_proven': False,
    }
    if not explore:
        return result
    if max_steps < 1:
        raise ValueError('max_steps must be positive')
    if initial_registers is None:
        initial_registers = {}
    if any(not 0 <= k <= 31 for k in initial_registers):
        raise ValueError('register indexes must be 0..31')
    memory = MappedMemory().map_region(base, image, writable=False)
    memory.map_region(matrix_address, bytes(MATRIX_SIZE), writable=True)
    regs = [0] * 32
    regs[5] = matrix_address
    for reg, value in initial_registers.items():
        if reg:
            regs[reg] = value
    trace = execute(image, base, start, memory, regs,
                    max_steps=max_steps, stop_pc=end)
    matrix_addresses = {matrix_address + off for off in MATRIX_OFFSETS}
    result['exploratory_trace'] = {
        'initial_registers_are_synthetic': True,
        'reason': trace['reason'],
        'reached_return_site': trace['completed'] and trace['reason'] == 'stop_pc',
        'executed_instructions': trace['executed'],
        'distinct_executed_pcs': len(set(trace['visited_pcs'])),
        'matrix_slot_store_count': sum(addr in matrix_addresses
                                       for addr in trace['store_addresses']),
        'all_matrix_slots_written': matrix_addresses.issubset(
            trace['store_addresses']),
    }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path, help='private extracted PS-X EXE')
    p.add_argument('--explore', action='store_true',
                   help='probe with synthetic zero-filled GPRs')
    p.add_argument('--max-steps', type=int, default=512)
    args = p.parse_args()
    print(json.dumps(analyze(args.exe.read_bytes(), explore=args.explore,
                             max_steps=args.max_steps), indent=2))


if __name__ == '__main__':
    main()
