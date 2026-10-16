"""Bounded path-sensitive MIPS provenance before a JAL call site.

Enumerates conservative conditional-branch outcomes with proper delay slots.
Rejects loops, paths leaving the window, and unsupported instructions;
never assumes a particular gameplay branch outcome or exposes game bytes.
"""
import struct
from collections import deque

try:
    from .mips_caller_sources import _step, _describe, initial_gprs, sign16
except ImportError:
    from mips_caller_sources import _step, _describe, initial_gprs, sign16


def _branch(word, pc, regs):
    """Return potential next PCs (post-delay slot), or None for nonbranch."""
    op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
    if op not in (1, 4, 5, 6, 7):
        return None
    if op == 1 and rt not in (0, 1):
        raise ValueError('unsupported REGIMM branch')
    if op in (6, 7) and rt:
        raise ValueError('reserved rt field in BLEZ/BGTZ')
    a, b = regs[rs].constant, regs[rt].constant
    known = None
    if op == 4 and a is not None and b is not None:
        known = a == b
    elif op == 5 and a is not None and b is not None:
        known = a != b
    elif op in (6, 7, 1) and a is not None:
        signed = a if a < 0x80000000 else a - 0x100000000
        known = (signed <= 0 if op == 6 else signed > 0 if op == 7
                 else signed < 0 if rt == 0 else signed >= 0)
    target = (pc + 4 + (sign16(word) << 2)) & 0xffffffff
    taken = target
    not_taken = (pc + 8) & 0xffffffff
    if known is None:
        return tuple(sorted({taken, not_taken}))
    return (taken if known else not_taken,)


def inspect(image, base, call, lookback_words=8, arguments=(4, 5, 6, 7),
            max_states=512, max_paths=64):
    """Join provenance across *all* bounded feasible control paths to call.

    An incoming unknown register makes a branch condition conservative; both
    successor paths must remain in the window and finish at the JAL. The
    routine deliberately refuses to infer through backward edges (loops).
    """
    if (not isinstance(lookback_words, int) or not 1 <= lookback_words <= 128
            or not isinstance(max_states, int) or max_states < 1
            or not isinstance(max_paths, int) or max_paths < 1
            or base % 4 or call % 4 or len(image) % 4
            or not all(isinstance(x, int) and 0 <= x < 32 for x in arguments)):
        raise ValueError('invalid MIPS CFG analysis parameters')
    first = call - 4 * lookback_words
    if first < base or call + 8 > base + len(image):
        return {'window_usable': False, 'reason': 'window_outside_image',
                'runtime_path_confirmed': False, 'arguments': []}

    def read(pc):
        if pc < first or pc > call + 4 or (pc - base) % 4:
            raise ValueError('branch target leaves caller window')
        return struct.unpack_from('<I', image, pc - base)[0]

    queue = deque([(first, initial_gprs(), None, None, None, frozenset())])
    outputs = []
    states = 0
    branches = 0
    try:
        while queue:
            states += 1
            if states > max_states:
                raise ValueError('state_limit')
            pc, regs, pending, hi, lo, seen = queue.popleft()
            if pc in seen or pc < first or pc > call:
                raise ValueError('loop_or_window_exit')
            seen = seen | {pc}
            word = read(pc)
            if pc == call:
                if word >> 26 != 3:
                    raise ValueError('expected JAL')
                # The JAL delay slot is mandatory and must not itself branch.
                slot = read(call + 4)
                if _branch(slot, call + 4, regs) is not None or slot >> 26 in (2, 3):
                    raise ValueError('branch in JAL delay slot')
                new_regs = regs.copy()
                after_jal, hi, lo = _step(word, new_regs, pending, hi, lo,
                                          at_call=True)
                final_pending, hi, lo = _step(slot, new_regs, after_jal, hi, lo)
                outputs.append((new_regs, final_pending))
                if len(outputs) > max_paths:
                    raise ValueError('path_limit')
                continue
            targets = _branch(word, pc, regs)
            if targets is None:
                if word >> 26 in (2, 3) or (word >> 26 == 0 and word & 63 in (8, 9)):
                    raise ValueError('unsupported jump before JAL')
                regs = regs.copy()
                pending, hi, lo = _step(word, regs, pending, hi, lo)
                queue.append((pc + 4, regs, pending, hi, lo, seen))
                continue
            # All supported conditional branches execute exactly one slot.
            if pc + 4 >= call:
                raise ValueError('branch delay slot overlaps JAL')
            branches += 1
            slot = read(pc + 4)
            if _branch(slot, pc + 4, regs) is not None or slot >> 26 in (2, 3):
                raise ValueError('branch in branch delay slot')
            if slot >> 26 == 0 and slot & 63 in (8, 9):
                raise ValueError('jump in branch delay slot')
            branch_regs = regs.copy()
            # The branch itself writes no general registers. Any preceding
            # load retires AFTER the branch has read its operands.
            if pending is not None and pending[0] != 0:
                branch_regs[pending[0]] = pending[1]
            branch_pending = None
            pending_after_slot, hi_after_slot, lo_after_slot = _step(
                slot, branch_regs, branch_pending, hi, lo)
            for target in targets:
                if target <= pc or target > call or target < first:
                    raise ValueError('branch target leaves window or loops')
                if target == pc + 4:
                    raise ValueError('branch target enters delay slot')
                queue.append((target, branch_regs.copy(), pending_after_slot,
                              hi_after_slot, lo_after_slot, seen | {pc + 4}))
    except ValueError as exc:
        return {'window_usable': False, 'reason': str(exc),
                'runtime_path_confirmed': False, 'arguments': []}

    if not outputs:
        return {'window_usable': False, 'reason': 'call_unreachable',
                'runtime_path_confirmed': False, 'arguments': []}
    desc = []
    for reg in arguments:
        versions = [regs[reg] for regs, pending in outputs]
        variations = [_describe(reg, value) for value in versions]
        desc.append({
            'gpr': reg,
            'source_kinds': sorted({v['source_kind'] for v in variations}),
            'incoming_gprs': sorted(set().union(*(set(v['incoming_gprs']) for v in variations))),
            'memory_kinds': sorted(set().union(*(set(v['memory_kinds']) for v in variations))),
            'same_origin_across_paths': len(set(versions)) == 1,
            'load_pending_on_any_path': any(pending is not None and pending[0] == reg
                                            for regs, pending in outputs),
        })
    return {'window_usable': True, 'reason': None,
            'runtime_path_confirmed': False,
            'paths_to_call': len(outputs),
            'conditional_branches_explored': branches,
            'all_explored_paths_reach_call': True,
            'external_entry_edges_ruled_out': False,
            'arguments': desc}
