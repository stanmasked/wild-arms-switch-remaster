"""Validate claimed MIPS BEQ/BNE executed-PC paths, including delay slots.

This checks syntactic consistency with an EXE, NOT execution provenance.
Only forward branches with literal NOP delay slots are modeled.
"""
try:
    from .audit_record_executed_access_claims import _WIDTH, _sign16
    from .audit_record_pointer_use import _POINTER_ADDS
except ImportError:
    from audit_record_executed_access_claims import _WIDTH, _sign16
    from audit_record_pointer_use import _POINTER_ADDS


def validate(words, site_pc, pcs, displacement, effective_address):
    """Return counts for a supported claimed trace, or None if unresolved.

    All eleven index/load-prefix instructions must occur in strict order.
    The remaining claimed PCs must follow either consecutive instruction
    flow or an allowed BEQ/BNE branch and its executed literal-NOP slot.
    A branch's actual predicate is never authenticated by its path.
    """
    if (not isinstance(words, (tuple, list)) or len(words) != 21
            or type(site_pc) is not int or type(displacement) is not int
            or type(effective_address) is not int
            or not isinstance(pcs, (tuple, list))
            or not 11 <= len(pcs) <= 21
            or any(type(pc) is not int for pc in pcs)):
        return None
    if tuple(pcs[:11]) != tuple(site_pc + i * 4 for i in range(11)):
        return None

    at = 11
    position = 11
    added = False
    branches = 0
    unknown_predicates = 0
    while position < len(pcs):
        if at < 11 or at >= len(words) or pcs[position] != site_pc + at * 4:
            return None
        word = words[at]
        op = word >> 26
        if word == 0:
            at += 1
            position += 1
            continue
        if word in _POINTER_ADDS and not added:
            added = True
            at += 1
            position += 1
            continue
        if op in (4, 5):
            # The immediately following instruction is always executed
            # on PS1 non-likely branches. Model only a NOP in that slot.
            if (at + 1 >= len(words) or words[at + 1] != 0
                    or position + 2 >= len(pcs)
                    or pcs[position + 1] != site_pc + (at + 1) * 4):
                return None
            rs = (word >> 21) & 31
            rt = (word >> 16) & 31
            dest = at + 1 + _sign16(word)
            fallthrough = at + 2
            if dest <= at + 1 or dest >= len(words):
                # Reject backwards/loop/slot/outside-window targets.
                return None
            if rs == rt:
                possibilities = {dest} if op == 4 else {fallthrough}
            else:
                possibilities = {dest, fallthrough}
                unknown_predicates += 1
            chosen = pcs[position + 2]
            candidate_indices = {i for i in possibilities
                                 if i < len(words)}
            if chosen not in {site_pc + i * 4 for i in candidate_indices}:
                return None
            at = (chosen - site_pc) // 4
            position += 2
            branches += 1
            continue
        if (added and op in _WIDTH
                and (word >> 21) & 31 == 3
                and _sign16(word) == displacement
                and effective_address % _WIDTH[op] == 0
                and position == len(pcs) - 1):
            return {'validated_branch_slots': branches,
                    'unknown_branch_predicates': unknown_predicates,
                    'hardware_predicate_authenticated': False}
        # Unsupported branch-likely, coprocessor op, J/JAL/JR, extra
        # arithmetic, non-NOP delay slot, memory before pointer ADDU.
        return None
    return None
