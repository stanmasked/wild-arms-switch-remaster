"""Infer dynamic GPR read-before-write dependencies from a bounded MIPS PC trace.

This reports only register numbers, never guest data, instruction words or
memory values. Conservative scope: supported integer instructions only.
An LW/LH/LB destination becomes visible *after* the following instruction.
"""


def accesses(word):
    """Return (read_gprs, immediate_write_gpr, delayed_load_gpr).

    A zero destination indicates no observable GPR write. Only call with
    instructions that the concrete MIPS runner has successfully executed.
    """
    op = word >> 26
    rs, rt, rd, fn = ((word >> 21) & 31, (word >> 16) & 31,
                      (word >> 11) & 31, word & 63)
    if word == 0:
        return set(), None, None
    if op == 0:
        if fn in (0, 2, 3):  # immediate shifts
            return {rt}, rd, None
        if fn in (4, 6, 7):
            return {rs, rt}, rd, None
        if fn in (8, 9):  # JR / JALR
            return {rs}, (rd if fn == 9 else None), None
        if fn in (16, 18):  # MFHI / MFLO
            return set(), rd, None
        if fn in (17, 19):  # MTHI / MTLO
            return {rs}, None, None
        if fn in (24, 25):  # MULT / MULTU
            return {rs, rt}, None, None
        if fn in (32, 33, 34, 35, 36, 37, 38, 39, 42, 43):
            return {rs, rt}, rd, None
    if op in (32, 33, 35, 36, 37):  # LB/LH/LW/LBU/LHU
        return {rs}, None, rt
    if op in (40, 41, 43):  # SB/SH/SW
        return {rs, rt}, None, None
    if op in (4, 5, 20, 21):  # BEQ/BNE/BEQL/BNEL
        return {rs, rt}, None, None
    if op in (6, 7, 22, 23, 1):  # sign tests / REGIMM
        return {rs}, None, None
    if op == 2:  # J
        return set(), None, None
    if op == 3:  # JAL
        return set(), 31, None
    if op in (8, 9, 10, 11, 12, 13, 14):
        return {rs}, rt, None
    if op == 15:  # LUI
        return set(), rt, None
    raise ValueError('unsupported MIPS instruction dependency')


def read_before_write(image, base, visited_pcs):
    """List GPRs read before a value becomes available on this executed path.

    These are possible external input dependencies, not proof of the values
    required by original gameplay. Unvisited paths and HI/LO are excluded.
    """
    import struct
    known = {0}
    needs = set()
    pending = None
    for pc in visited_pcs:
        offset = pc - base
        if offset < 0 or offset % 4 or offset + 4 > len(image):
            raise ValueError('executed PC outside supplied code image')
        word, = struct.unpack_from('<I', image, offset)
        reads, immediate_write, load_dest = accesses(word)
        needs.update(r for r in reads if r not in known and r != 0)
        # Prior load is committed after the current instruction has read its
        # registers. A current GPR write to the same destination supersedes it.
        if pending and pending != immediate_write and pending != load_dest:
            known.add(pending)
        if immediate_write:
            known.add(immediate_write)
        pending = load_dest if load_dest else None
    return tuple(sorted(needs))
