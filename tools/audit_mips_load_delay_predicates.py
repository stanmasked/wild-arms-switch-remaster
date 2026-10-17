"""Bounded MIPS-I delayed-load and BEQ/BNE predicate-claim consistency audit.

An unauthenticated register/load-value/PC claim is NOT a hardware trace.
Only NOP, LW, SLL, ADDU, and ordinary BEQ/BNE with NOP slots are modeled.
"""
import argparse
import json
import re
from pathlib import Path

SCHEMA = 'wild-arms-ps1-load-delay-predicate-claims-v1'
REPORT_SCHEMA = 'wild-arms-ps1-load-delay-predicate-audit-v1'
MAX_FILE_BYTES = 64 * 1024
MAX_STEPS = 32
_HEX = re.compile(r'0[xX][0-9a-fA-F]{8}\Z')
_U32 = 0xffffffff


def _hex_u32(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError('invalid private unsigned word')
    return int(value, 16)


def _signed_16(word):
    imm = word & 0xffff
    return imm - 65536 if imm & 32768 else imm


def analyze(reference):
    """Check a self-reported short PC trace with one-slot delayed LW writes.

    Branch operands read registers BEFORE a pending load from the previous
    step is committed. The branch's NOP delay slot is always executed.
    Reg-value collisions/unsupported opcodes fail closed.
    """
    if (type(reference) is not dict or set(reference) != {
            'schema', 'source', 'initial_gprs_u32', 'steps'}
            or reference['schema'] != SCHEMA
            or reference['source'] not in ('synthetic', 'external_ps1_capture_claim')):
        raise ValueError('invalid claim schema')
    initial = reference['initial_gprs_u32']
    steps = reference['steps']
    if (type(initial) is not dict or len(initial) > 31
            or type(steps) is not list or not 3 <= len(steps) <= MAX_STEPS):
        raise ValueError('invalid claimed registers or steps')
    regs = {0: 0}
    for index, value in initial.items():
        if (type(index) is not str or not index.isdecimal()
                or str(int(index)) != index or not 1 <= int(index) <= 31):
            raise ValueError('invalid initial GPR name')
        regs[int(index)] = _hex_u32(value)

    parsed = []
    for item in steps:
        if type(item) is not dict or not {'pc_u32', 'word_u32'} <= set(item):
            raise ValueError('invalid claimed instruction fields')
        if set(item) - {'pc_u32', 'word_u32', 'load_result_u32', 'claimed_taken'}:
            raise ValueError('unexpected private claim field')
        pc = _hex_u32(item['pc_u32'])
        word = _hex_u32(item['word_u32'])
        if pc & 3:
            raise ValueError('unaligned claimed PC')
        parsed.append((pc, word, item))
    if len({pc for pc, _, _ in parsed}) != len(parsed):
        raise ValueError('repeated claimed PC')

    expected_pc = parsed[0][0]
    pending = None
    post_slot_pc = None
    checked_loads = checked_branches = hazards = checked_slots = 0

    for i, (pc, word, item) in enumerate(parsed):
        if pc != expected_pc:
            raise ValueError('claimed PC transition mismatch')
        op = word >> 26
        rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        shift, fn = (word >> 6) & 31, word & 63
        is_slot = post_slot_pc is not None
        if is_slot and word != 0:
            raise ValueError('unsupported non-NOP branch delay slot')
        direct_write = None
        new_pending = None
        branch_next = None
        if word == 0:
            kind = 'nop'
        elif op == 35:  # LW rt,imm(rs); memory value supplied by caller.
            kind = 'load'
            if (rt == 0 or set(item) != {
                    'pc_u32', 'word_u32', 'load_result_u32'}
                    or rs not in regs):
                raise ValueError('unknown LW base or missing load result')
            addr = regs[rs] + _signed_16(word)
            if not 0 <= addr <= _U32 or addr & 3:
                raise ValueError('unsupported wrapped/unaligned LW address')
            new_pending = (rt, _hex_u32(item['load_result_u32']))
            checked_loads += 1
        elif op == 0 and fn == 0 and rs == 0:  # SLL
            kind = 'sll'
            if rt not in regs:
                raise ValueError('unknown SLL source')
            direct_write = (rd, (regs[rt] << shift) & _U32)
        elif op == 0 and fn == 33 and shift == 0:  # ADDU
            kind = 'addu'
            if rs not in regs or rt not in regs:
                raise ValueError('unknown ADDU source')
            direct_write = (rd, (regs[rs] + regs[rt]) & _U32)
        elif op in (4, 5):  # BEQ/BNE: read values BEFORE pending load retires.
            kind = 'branch'
            if (set(item) != {'pc_u32', 'word_u32', 'claimed_taken'}
                    or type(item['claimed_taken']) is not bool
                    or rs not in regs or rt not in regs or i + 2 >= len(parsed)):
                raise ValueError('missing GPR/branch claim/delay slot')
            actual = (regs[rs] == regs[rt])
            if op == 5:
                actual = not actual
            if item['claimed_taken'] != actual:
                raise ValueError('claimed branch contradicts pre-retirement GPRs')
            target = pc + 4 + _signed_16(word) * 4
            fallthrough = pc + 8
            branch_next = target if actual else fallthrough
            # For this strictly forward-only oracle even an untaken
            # backwards branch is unsupported: its encoded target must
            # stay outside the branch/slot itself.
            if (not fallthrough <= target <= _U32
                    or not fallthrough <= branch_next <= _U32
                    or branch_next & 3):
                raise ValueError('unsupported backward/out-of-range branch')
            if parsed[i + 1][0] != pc + 4 or parsed[i + 1][1] != 0:
                raise ValueError('branch NOP slot missing')
            if parsed[i + 2][0] != branch_next:
                raise ValueError('claimed next PC contradicts branch')
            checked_branches += 1
            if pending is not None and pending[0] in (rs, rt):
                hazards += 1
        else:
            raise ValueError('unsupported opcode in private claim')

        # Every non-NOP operation has an explicitly restricted schema.
        if kind not in ('load', 'branch') and set(item) != {'pc_u32', 'word_u32'}:
            raise ValueError('unexpected claimed register payload')
        # The instruction at i reads the *old* register state. Retire the
        # load from i-1 only after this read, and before the next instruction.
        if pending is not None:
            if direct_write is not None and direct_write[0] == pending[0]:
                raise ValueError('unsupported simultaneous load/register write')
            if new_pending is not None and new_pending[0] == pending[0]:
                raise ValueError('unsupported overlapping LW destination')
            regs[pending[0]] = pending[1]
        pending = new_pending
        if direct_write is not None and direct_write[0]:
            regs[direct_write[0]] = direct_write[1]

        if is_slot:
            checked_slots += 1
            expected_pc = post_slot_pc
            post_slot_pc = None
        elif branch_next is not None:
            expected_pc = pc + 4
            post_slot_pc = branch_next
        else:
            expected_pc = pc + 4

    if post_slot_pc is not None or checked_branches == 0 or checked_loads == 0:
        raise ValueError('incomplete branch/load claim')
    return {
        'schema': REPORT_SCHEMA,
        'claimed_instructions_checked': len(parsed),
        'claimed_lw_results_consumed': checked_loads,
        'claimed_beq_bne_predicates_checked': checked_branches,
        'branches_comparing_pre_retirement_loaded_register': hazards,
        'mandatory_nop_delay_slots_checked': checked_slots,
        'synthetic_or_claimed_trace_self_consistent': True,
        'claimed_external_capture': reference['source'] == 'external_ps1_capture_claim',
        'input_registers_or_addresses_emitted': False,
        'original_ps1_execution_authenticated': False,
        'original_ps1_pipeline_cycle_accuracy_verified': False,
        'game_record_layout_verified': False,
        'nintendo_switch_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_claim', type=Path)
    args = parser.parse_args(argv)
    try:
        with args.private_claim.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError('oversized private claim')
        report = analyze(json.loads(raw.decode('utf-8')))
    except (OSError, UnicodeError, ValueError, TypeError,
            KeyError, IndexError, OverflowError, RecursionError):
        print(json.dumps({'schema': REPORT_SCHEMA, 'valid_input': False,
                          'error_code': 'invalid_private_input',
                          'input_registers_or_addresses_emitted': False},
                         sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
