"""Bounded, privacy-safe static base-pointer provenance and branch-path audit.

An exact signature describes code bytes only, never proves authentic PS1
execution, a genuine record size, or the pointer value at runtime.
"""
import argparse
import json
from collections import deque
from pathlib import Path

try:
    from .verify_record_stride import (
        TARGETS, GLOBAL_WORDS, _static_index_scale, read_raw_iso_entry,
    )
    from .audit_record_pointer_use import (
        WINDOW_WORDS, MAX_EXE_BYTES, _POINTER_ADDS, _MEMORY_OPS,
    )
except ImportError:
    from verify_record_stride import (
        TARGETS, GLOBAL_WORDS, _static_index_scale, read_raw_iso_entry,
    )
    from audit_record_pointer_use import (
        WINDOW_WORDS, MAX_EXE_BYTES, _POINTER_ADDS, _MEMORY_OPS,
    )

SCHEMA = 'wild-arms-ps1-record-base-provenance-v1'
MAX_STATES = 64
MAX_TERMINALS = 32


def _sign16(word):
    value = word & 0xffff
    return value - 0x10000 if value & 0x8000 else value


def _prefix_has_one_instruction_load_gap(words):
    """Check the LUI -> LW register dependency and one-instruction gap.

    This recognizes only a syntactic chain, not an observed memory value.
    The exact opcode signature is additionally checked by the caller.
    """
    lui, load, gap = words[8:11]
    if (lui >> 26 != 15 or (lui >> 21) & 31 or
            (lui >> 16) & 31 != 3 or
            load >> 26 != 35 or (load >> 21) & 31 != 3 or
            (load >> 16) & 31 != 3 or
            gap != 0x00021080):
        raise ValueError('unverified base-pointer load chain')
    return True


def _trace_tail(words):
    """Enumerate conservative BEQ/BNE paths with mandatory NOP delay slots.

    A result is only a candidate instruction *shape*; no RAM is read and no
    input condition is claimed to have been observed on hardware.
    """
    if not isinstance(words, (tuple, list)) or len(words) > WINDOW_WORDS - 11:
        raise ValueError('invalid bounded tail')
    queue = deque([(0, False)])
    visited = set()
    terminal_success = 0
    terminal_unknown = 0
    known_branches = 0
    unknown_branches = 0
    while queue:
        if len(visited) >= MAX_STATES or terminal_success + terminal_unknown > MAX_TERMINALS:
            return {'success': 0, 'unknown': 1, 'known_branches': known_branches,
                    'unknown_branches': unknown_branches, 'bounded_out': True}
        pc, added = queue.popleft()
        state = (pc, added)
        if pc < 0 or pc >= len(words):
            terminal_unknown += 1
            continue
        # Forward-only successors make repeated states safe to coalesce.
        # Do not count such convergence as an unresolved path.
        if state in visited:
            continue
        visited.add(state)
        word = words[pc]
        if word == 0:
            queue.append((pc + 1, added))
            continue
        if word in _POINTER_ADDS and not added:
            queue.append((pc + 1, True))
            continue
        op = word >> 26
        if op in _MEMORY_OPS and (word >> 21) & 31 == 3 and added:
            terminal_success += 1
            continue
        if op in (4, 5):  # Only ordinary, non-likely BEQ/BNE.
            # Delay-slot control flow or loads/stores are conservatively
            # refused: only a literal NOP is accepted in that slot.
            if pc + 1 >= len(words) or words[pc + 1] != 0:
                terminal_unknown += 1
                continue
            rs, rt = (word >> 21) & 31, (word >> 16) & 31
            target = pc + 1 + _sign16(word)
            fallthrough = pc + 2
            if rs == rt:
                known_branches += 1
                successors = (target,) if op == 4 else (fallthrough,)
            else:
                unknown_branches += 1
                successors = tuple(sorted({target, fallthrough}))
            for dest in successors:
                if dest <= pc + 1 or dest >= len(words):
                    terminal_unknown += 1
                else:
                    queue.append((dest, added))
            continue
        # Unsupported opcode, another ADDU, earlier base-v1 memory access,
        # J/JAL, JR/JALR, REGIMM/likely branch, or coprocessor control:
        # do not invent an execution path or inferred pointer value.
        terminal_unknown += 1
    return {'success': terminal_success, 'unknown': terminal_unknown,
            'known_branches': known_branches,
            'unknown_branches': unknown_branches, 'bounded_out': False}


def inspect(exe_data):
    if (not isinstance(exe_data, (bytes, bytearray)) or
            len(exe_data) < 2048 or exe_data[:8] != b'PS-X EXE'):
        raise ValueError('invalid PS-X EXE')
    base = int.from_bytes(exe_data[0x18:0x1c], 'little')
    size = int.from_bytes(exe_data[0x1c:0x20], 'little')
    if not 0 < size <= MAX_EXE_BYTES or 2048 + size > len(exe_data):
        raise ValueError('invalid bounded EXE')
    all_paths_sites = some_paths_sites = unresolved_sites = 0
    known_branches = unknown_branches = limited_sites = 0
    for target in TARGETS:
        offset = 2048 + target - base
        if offset < 2048 or offset + WINDOW_WORDS * 4 > 2048 + size:
            raise ValueError('record base-provenance window outside EXE')
        words = [int.from_bytes(exe_data[offset + n:offset + n + 4], 'little')
                 for n in range(0, WINDOW_WORDS * 4, 4)]
        if _static_index_scale(words[:8], words[8:11]) != 2708:
            raise ValueError('unverified index coefficient')
        _prefix_has_one_instruction_load_gap(words)
        result = _trace_tail(words[11:])
        known_branches += result['known_branches']
        unknown_branches += result['unknown_branches']
        limited_sites += bool(result['bounded_out'])
        if result['success'] and not result['unknown']:
            all_paths_sites += 1
        elif result['success']:
            some_paths_sites += 1
        else:
            unresolved_sites += 1
    return {
        'schema': SCHEMA,
        'matching_global_load_chain_sites': len(TARGETS),
        'load_delay_gap_syntactically_present_sites': len(TARGETS),
        'index_coefficient_from_checked_in_opcodes': 2708,
        'all_enumerated_paths_reach_candidate_access_sites': all_paths_sites,
        'some_paths_reach_candidate_access_sites': some_paths_sites,
        'unresolved_sites': unresolved_sites,
        'known_predicate_branches_examined': known_branches,
        'unknown_predicate_branches_examined': unknown_branches,
        'bounded_analysis_limit_sites': limited_sites,
        'global_pointer_contents_known': False,
        'original_ps1_execution_verified': False,
        'record_size_verified': False,
        'native_switch_build_verified': False,
        'private_game_data_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path,
                        help='Private inspect_disc.py --json inventory')
    args = parser.parse_args(argv)
    try:
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        candidates = [row for row in entries if isinstance(row, dict)
                      and row.get('path') == '/EXE/WILDARMS.EXE;1'
                      and not row.get('directory', False)]
        if len(candidates) != 1:
            raise ValueError('invalid private inventory')
        report = inspect(read_raw_iso_entry(args.disc, candidates[0]))
    except (OSError, UnicodeError, ValueError, TypeError,
            KeyError, IndexError, OverflowError):
        print(json.dumps({'schema': SCHEMA, 'valid_input': False,
                          'error_code': 'invalid_private_input',
                          'private_game_data_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
