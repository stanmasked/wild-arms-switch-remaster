"""Bounded, concrete PS1 MIPS integer control-flow replay.

Executes a subset of MIPS integer instructions with delay slots and one-cycle
load delay. Branch conditions are evaluated BEFORE the delay-slot instruction.
No GTE, dynamic address aliases, exceptions, coprocessors, or code mutation.
Unsupported operations terminate with an explicit reason. The in-process
trace now contains private written values in store_value_accesses; never
publish that raw trace when replaying original game data.
"""
import struct

try:
    from .mips_fixed32 import s32, u32, sign_extend16
    from .mips_integer_step import step
    from .mips_arithmetic_event_sequence import executed_event
except ImportError:
    from mips_fixed32 import s32, u32, sign_extend16
    from mips_integer_step import step
    from mips_arithmetic_event_sequence import executed_event


LOADS = {32: 1, 33: 2, 35: 4, 36: 1, 37: 2}
STORES = {40: 1, 41: 2, 43: 4}


def _control(word, pc, regs):
    """(is_control, target, likely_annulled, link_register) or None.

    A target of pc+8 is the fallthrough after the mandatory delay slot.
    """
    op = word >> 26
    rs, rt = (word >> 21) & 31, (word >> 16) & 31
    imm = sign_extend16(word)
    target = u32(pc + 4 + (imm << 2))
    if op in (4, 5, 6, 7, 20, 21, 22, 23):
        if op in (6, 7, 22, 23) and rt != 0:
            raise ValueError('reserved rt bits in BLEZ/BGTZ encoding')
        if op in (4, 20): taken = regs[rs] == regs[rt]
        elif op in (5, 21): taken = regs[rs] != regs[rt]
        elif op in (6, 22): taken = s32(regs[rs]) <= 0
        else: taken = s32(regs[rs]) > 0
        return target if taken else u32(pc + 8), (op >= 20 and not taken), None
    if op == 1:
        if rt not in (0, 1, 2, 3):
            raise ValueError('unsupported REGIMM control instruction')
        taken = s32(regs[rs]) < 0 if rt in (0, 2) else s32(regs[rs]) >= 0
        return target if taken else u32(pc + 8), (rt in (2, 3) and not taken), None
    if op in (2, 3):
        target = u32(((pc + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2))
        return target, False, (31 if op == 3 else None)
    if op == 0 and (word & 63) in (8, 9):
        rd, sa = (word >> 11) & 31, (word >> 6) & 31
        fn = word & 63
        if rt or sa or (fn == 8 and rd):
            raise ValueError('malformed JR/JALR encoding')
        return regs[rs], False, (rd if fn == 9 else None)
    return None


def _gpr_destination(word):
    """Identify writes that supersede an older pending LW result."""
    op = word >> 26
    rt, rd, fn = (word >> 16) & 31, (word >> 11) & 31, word & 63
    if op in LOADS or op in (8, 9, 10, 11, 12, 13, 14, 15):
        return rt
    if op == 0 and fn in (0, 2, 3, 4, 6, 7, 16, 18,
                          32, 33, 34, 35, 36, 37, 38, 39, 42, 43):
        return rd
    return None


def execute(image, base, start, memory, gpr=None, hi=0, lo=0,
            max_steps=4096, stop_pc=None, initial_pending_load=None):
    """Run a bounded image slice; report state, PC trace, and exact halt cause.

    State is returned for host-side tests only; callers should not publish
    registers obtained from private original game memory.
    """
    if (base & 3 or start & 3 or len(image) & 3 or
            start < base or start >= base + len(image) or max_steps < 0):
        raise ValueError('invalid code address, length or step limit')
    if gpr is None:
        gpr = [0] * 32
    if len(gpr) != 32:
        raise ValueError('expected 32 MIPS GPRs')
    regs = tuple([0] + [u32(v) for v in gpr[1:]])
    hi, lo = u32(hi), u32(lo)
    if initial_pending_load is not None:
        if (not isinstance(initial_pending_load, (tuple, list)) or
                len(initial_pending_load) != 2 or
                type(initial_pending_load[0]) is not int or
                not 1 <= initial_pending_load[0] <= 31 or
                type(initial_pending_load[1]) is not int or
                not 0 <= initial_pending_load[1] <= 0xffffffff):
            raise ValueError('invalid captured pending MIPS load state')
        initial_pending_load = tuple(initial_pending_load)
    pc = start
    pending_load = initial_pending_load
    delayed_target = None
    visited = []
    writes = []
    store_accesses = []
    store_value_accesses = []
    arithmetic_accesses = []
    loads = []
    completed_transfers = []
    pending_transfer = None

    def result(completed, reason):
        return {'completed': completed, 'reason': reason, 'pc': pc,
                'executed': len(visited), 'visited_pcs': tuple(visited),
                'store_addresses': tuple(writes),
                'store_accesses': tuple(store_accesses),
                'store_value_accesses': tuple(store_value_accesses),
                'arithmetic_accesses': tuple(arithmetic_accesses),
                'load_accesses': tuple(loads),
                'control_transfers': tuple(completed_transfers), 'gpr': regs,
                'hi': hi, 'lo': lo, 'pending_load': pending_load}

    while True:
        if stop_pc is not None and pc == stop_pc and delayed_target is None:
            return result(True, 'stop_pc')
        if pc == base + len(image) and delayed_target is None:
            return result(True, 'end_of_image')
        if pc < base or pc + 4 > base + len(image) or pc & 3:
            return result(False, 'pc_outside_image')
        if len(visited) >= max_steps:
            return result(False, 'step_limit')

        word = struct.unpack_from('<I', image, pc - base)[0]
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        was_delay_slot = delayed_target is not None
        try:
            control = _control(word, pc, regs)
            if was_delay_slot and control is not None:
                raise ValueError('branch in delay slot is unsupported')
            updated = regs
            next_hi, next_lo = hi, lo
            next_pending = None
            store_addr = None
            regs_before_store_value = regs[rt] if op in STORES else 0
            load_access = None
            destination = _gpr_destination(word)
            annul = False
            next_pc = u32(pc + 4)
            next_delayed_target = None
            next_pending_transfer = None
            arithmetic_event = None
            if control is not None:
                target, annul, link = control
                if link is not None:
                    updated = list(regs)
                    updated[link] = u32(pc + 8)
                    destination = link
                if op == 0:
                    kind = 'jr_ra' if (word & 63) == 8 and rs == 31 else (
                        'jr' if (word & 63) == 8 else 'jalr')
                elif op == 2:
                    kind = 'j'
                elif op == 3:
                    kind = 'jal'
                else:
                    kind = 'branch'
                descriptor = (pc, kind, target)
                if annul:
                    next_pc = u32(pc + 8)
                    completed_transfers.append(descriptor)
                else:
                    next_delayed_target = target
                    next_pending_transfer = descriptor
            elif op in LOADS or op in STORES:
                addr = u32(regs[rs] + sign_extend16(word))
                if op in LOADS:
                    value = memory.read(addr, LOADS[op], signed=op in (32, 33))
                    next_pending = (rt, value) if rt else None
                    load_access = (pc, addr, LOADS[op], rt)
                else:
                    memory.write(addr, STORES[op], regs[rt])
                    store_addr = addr
            else:
                updated, next_hi, next_lo = step(word, regs, hi, lo)
                arithmetic_event = executed_event(pc, word, updated, next_hi, next_lo)

            updated = list(updated)
            if pending_load is not None:
                old_dest, old_value = pending_load
                # An *immediate* ALU write supersedes an older load, but
                # another LW/LH to the same GPR remains pending for a later
                # instruction. The older load must retire at this boundary.
                if old_dest != destination or op in LOADS:
                    updated[old_dest] = old_value
            regs = tuple([0] + updated[1:])
            hi, lo = next_hi, next_lo
            pending_load = next_pending
            if was_delay_slot:
                next_pc = delayed_target
                next_delayed_target = None
                if pending_transfer is not None:
                    completed_transfers.append(pending_transfer)
                next_pending_transfer = None
            visited.append(pc)
            if arithmetic_event is not None:
                arithmetic_accesses.append(arithmetic_event)
            if store_addr is not None:
                writes.append(store_addr)
                store_accesses.append((pc, store_addr, STORES[op], rt))
                # Private exact *written* bit pattern, truncated by SB/SH/SW.
                # Register value is sampled before the instruction retires a
                # delayed load; never publish it in a sanitized report.
                store_value_accesses.append((pc, store_addr, STORES[op], rt,
                    regs_before_store_value & ((1 << (8 * STORES[op])) - 1)))
            if load_access is not None:
                loads.append(load_access)
            pc, delayed_target = next_pc, next_delayed_target
            pending_transfer = next_pending_transfer
        except (ValueError, OverflowError) as exc:
            return result(False, type(exc).__name__)
