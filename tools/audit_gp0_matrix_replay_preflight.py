#!/usr/bin/env python3
"""Private PS-X EXE MIPS matrix preflight: aggregate counts, no game data output.

An optional exploratory replay uses synthetic zero registers, not gameplay
state. Never exposes executable words, table entries, registers or coefficients.
"""
import argparse
import json
import struct
from collections import Counter

STACK_BASE = 0x80120000
STACK_SIZE = 0x1000
STACK_POINTER_MARGIN = 0x80
from pathlib import Path
try:
    from .audit_original_nclip_winding import parse_exe
    from .audit_gp0_rotation_matrix_builder import BUILDER, RETURN, CALL, jal_target
    from .audit_gp0_trig_table import TABLE, ENTRIES
    from .mips_control_flow import execute, LOADS, STORES
    from .mips_matrix_memory import MappedMemory, MATRIX_OFFSETS, MATRIX_SIZE
    from .mips_entry_dependencies import read_before_write
    from .mips_call_boundary import analyze_boundary
    from .mips_caller_sources import inspect as inspect_caller_sources
    from .mips_input_sensitivity import probe_input_registers
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from audit_gp0_rotation_matrix_builder import BUILDER, RETURN, CALL, jal_target
    from audit_gp0_trig_table import TABLE, ENTRIES
    from mips_control_flow import execute, LOADS, STORES
    from mips_matrix_memory import MappedMemory, MATRIX_OFFSETS, MATRIX_SIZE
    from mips_entry_dependencies import read_before_write
    from mips_call_boundary import analyze_boundary
    from mips_caller_sources import inspect as inspect_caller_sources
    from mips_input_sensitivity import probe_input_registers


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
        return 'branch', not (op in (6, 7, 22, 23) and rt != 0)
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


def inspect_caller(image, base, call=CALL, builder=BUILDER):
    """Check the known JAL and the caller's ADDIU a1,sp,16 pattern.

    Only boolean results are exposed; no executable bytes are returned.
    """
    found = (call - 16 >= base and call + 4 <= base + len(image)
             and (call - base) % 4 == 0)
    if not found:
        return {'callsite_in_image': False, 'jal_targets_builder': False,
                'a1_is_sp_plus_16': False, 'linkage_confirmed': False}
    jal, = struct.unpack_from('<I', image, call - base)
    setup, = struct.unpack_from('<I', image, call - 16 - base)
    target_ok = jal_target(jal, call) == builder
    pointer_ok = (setup >> 26 in (8, 9)
                  and ((setup >> 21) & 31) == 29
                  and ((setup >> 16) & 31) == 5
                  and (setup & 65535) == 16)
    return {'callsite_in_image': True, 'jal_targets_builder': target_ok,
            'a1_is_sp_plus_16': pointer_ok,
            'linkage_confirmed': target_ok and pointer_ok}


def analyze(blob, start=BUILDER, end=RETURN, *, table=TABLE,
            matrix_address=0x80110000, explore=False, max_steps=512,
            initial_registers=None, frame_layout=False, call=CALL,
            caller_replay=False, input_sensitivity=False, sensitivity_delta=1,
            caller_lookback=4):
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
        'caller_linkage': inspect_caller(image, base, call=call, builder=start),
        'caller_argument_sources': inspect_caller_sources(
            image, base, call, lookback_words=caller_lookback),
        'original_game_state_known': False,
        'bit_exact_original_coefficients_proven': False,
    }
    if input_sensitivity and not caller_replay:
        raise ValueError('input sensitivity requires verified caller replay')
    if caller_replay:
        # Only run verified ADDIU a1,sp,16 + JAL builder callsites.
        if not result['caller_linkage']['linkage_confirmed']:
            raise ValueError('caller instructions do not match expected linkage')
        explore = True
        frame_layout = True
    if not explore:
        return result
    if max_steps < 1:
        raise ValueError('max_steps must be positive')
    if initial_registers is None:
        initial_registers = {}
    if any(not isinstance(k, int) or not 0 <= k <= 31
           for k in initial_registers):
        raise ValueError('register indexes must be 0..31')
    if frame_layout and ({5, 29} & set(initial_registers)):
        raise ValueError('frame_layout owns a1 and sp register seeds')
    memory = MappedMemory().map_region(base, image, writable=False)
    stack_pointer = STACK_BASE + STACK_SIZE - (
        STACK_POINTER_MARGIN if frame_layout else 0x20)
    if frame_layout:
        # Caller sets a1=sp+16 at CALL-16. Matrix lives INSIDE the
        # bounded writable stack, not in a separately mapped region.
        matrix_address = stack_pointer + 16
        memory.map_region(STACK_BASE, bytes(STACK_SIZE), writable=True)
    else:
        memory.map_region(matrix_address, bytes(MATRIX_SIZE), writable=True)
        memory.map_region(STACK_BASE, bytes(STACK_SIZE), writable=True)
    regs = [0] * 32
    regs[5] = 0 if caller_replay else matrix_address
    regs[29] = stack_pointer
    for reg, value in initial_registers.items():
        if reg:
            regs[reg] = value
    replay_entry = call - 16 if caller_replay else start
    expected_stop = call + 8 if caller_replay else end
    trace = execute(image, base, replay_entry, memory, regs,
                    max_steps=max_steps, stop_pc=expected_stop)
    matrix_addresses = {matrix_address + off for off in MATRIX_OFFSETS}
    visited_counts = Counter(instruction_family(struct.unpack_from(
        '<I', image, pc-base)[0])[0] for pc in trace['visited_pcs'])
    halt_family = None
    halt_category = None
    if not trace['completed'] and trace['reason'] in ('ValueError', 'OverflowError'):
        halt_pc = trace['pc']
        if base <= halt_pc < base + len(image) and (halt_pc-base) % 4 == 0:
            halt_word = struct.unpack_from('<I', image, halt_pc-base)[0]
            halt_family, halt_supported = instruction_family(halt_word)
            if not halt_supported:
                halt_category = 'unsupported_instruction'
            elif halt_family in ('aligned_load', 'aligned_store'):
                halt_category = 'memory_access_or_alignment'
            else:
                halt_category = 'execution_semantics_or_overflow'
    unique_matrix_stores = set(trace['store_addresses']) & matrix_addresses
    visited = trace['visited_pcs']
    # A completed JR $ra transfer proves its delay slot has run.
    # A direct jump or a failed delay slot cannot count as a return.
    transfers = trace['control_transfers']
    return_instruction_executed = bool(caller_replay and any(
        source == end and kind == 'jr_ra'
        for source, kind, target in transfers))
    returned = bool(caller_replay and trace['completed']
                    and trace['reason'] == 'stop_pc'
                    and (call, 'jal', start) in transfers
                    and (end, 'jr_ra', call + 8) in transfers
                    and start in visited)
    result['exploratory_trace'] = {
        'initial_registers_are_synthetic': True,
        'read_before_first_write_gprs': list(read_before_write(image, base, visited)),
        'call_boundary': (analyze_boundary(image, base, visited, start)
                          if caller_replay else None),
        'synthetic_stack_mapped': True,
        'frame_layout': 'a1_sp_plus_16' if frame_layout else 'separate_matrix',
        'replay_origin': 'caller_before_jal' if caller_replay else 'builder_entry',
        'caller_jal_executed': bool(caller_replay and call in visited),
        'builder_entry_reached': start in visited or (
            caller_replay and call in visited and trace['pc'] == start),
        'returned_to_caller': bool(returned),
        'executed_instruction_families': dict(sorted(visited_counts.items())),
        'halt_instruction_family': halt_family,
        'halt_category': halt_category,
        'return_instruction_executed': return_instruction_executed,
        'reason': trace['reason'],
        'reached_return_site': (return_instruction_executed if caller_replay else
                                trace['completed'] and trace['reason'] == 'stop_pc'),
        'executed_instructions': trace['executed'],
        'distinct_executed_pcs': len(set(trace['visited_pcs'])),
        'matrix_slot_store_count': sum(addr in matrix_addresses
                                       for addr in trace['store_addresses']),
        'distinct_matrix_slots_written': len(unique_matrix_stores),
        'all_matrix_slots_written': matrix_addresses.issubset(
            trace['store_addresses']),
    }
    if input_sensitivity:
        # Allocate fresh writable scratch memory for EVERY variation.
        # The resulting private coefficient values never leave this scope.
        def one_profile(register, amount):
            scratch = MappedMemory().map_region(base, image, writable=False)
            scratch.map_region(STACK_BASE, bytes(STACK_SIZE), writable=True)
            initial = [0] * 32
            initial[29] = stack_pointer
            for index, value in initial_registers.items():
                if index:
                    initial[index] = value
            if register is not None:
                initial[register] = (initial[register] + amount) & 0xffffffff
            trial = execute(image, base, replay_entry, scratch, initial,
                            max_steps=max_steps, stop_pc=expected_stop)
            returned = (trial['completed'] and trial['reason'] == 'stop_pc'
                        and (call, 'jal', start) in trial['control_transfers']
                        and (end, 'jr_ra', call + 8) in trial['control_transfers']
                        and start in trial['visited_pcs'])
            written = {addr - matrix_address for addr in trial['store_addresses']
                       if addr in matrix_addresses}
            coefficients = tuple(scratch.read(matrix_address + off, 2)
                                 for off in MATRIX_OFFSETS)
            return {'returned': returned, 'visited': trial['visited_pcs'],
                    'written_offsets': written, 'coefficients': coefficients}

        result['input_sensitivity'] = probe_input_registers(
            one_profile, delta=sensitivity_delta)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path, help='private extracted PS-X EXE')
    p.add_argument('--explore', action='store_true',
                   help='probe with synthetic zero-filled GPRs')
    p.add_argument('--max-steps', type=int, default=512)
    p.add_argument('--caller-lookback', type=int, default=4,
                   help='straight-line instructions to audit before JAL (1..128)')
    p.add_argument('--frame-layout', action='store_true',
                   help='probe synthetic a1=sp+16 stack-resident matrix')
    p.add_argument('--input-sensitivity', action='store_true',
                   help='compare synthetic a0/a2/a3 changes without showing coefficients')
    p.add_argument('--sensitivity-delta', type=int, default=1,
                   help='synthetic input variation (default +1)')
    p.add_argument('--caller-replay', action='store_true',
                   help='execute JAL from caller; implies --explore and --frame-layout')
    args = p.parse_args()
    print(json.dumps(analyze(args.exe.read_bytes(), explore=args.explore,
                             max_steps=args.max_steps,
                             frame_layout=args.frame_layout,
                             caller_replay=args.caller_replay,
                             input_sensitivity=args.input_sensitivity,
                             sensitivity_delta=args.sensitivity_delta,
                     caller_lookback=args.caller_lookback), indent=2))


if __name__ == '__main__':
    main()
