"""Synthetic machine-code checks; no private Wild Arms executable bytes."""
import struct
import unittest

from tools.mips_control_flow import execute
from tools.mips_matrix_memory import (
    TABLE_ADDRESS, prepare_matrix_memory, matrix_coefficients)
from tools.mips_trig_memory import synthetic_cardinal_table
from tools.mips_memory_sequence import Memory

CODE = 0x80010000
MATRIX = 0x80110000


def imm(op, rs, rt, val):
    return (op << 26) | (rs << 21) | (rt << 16) | (val & 65535)


def reg(fn, rs=0, rt=0, rd=0, shift=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (shift << 6) | fn


def jump(pc):
    return 2 << 26 | ((pc >> 2) & 0x3ffffff)


def run(words, registers=None, memory=None, **kwargs):
    if memory is None:
        memory = Memory(0x1000, bytes(32))
    return execute(struct.pack('<%dI' % len(words), *words), CODE, CODE,
                   memory, registers, **kwargs)


class MIPSControlFlowTests(unittest.TestCase):
    def test_taken_branch_executes_slot_and_skips_fallthrough(self):
        registers = [0] * 32
        registers[8] = registers[9] = 3
        result = run([imm(4, 8, 9, 2), imm(9, 0, 10, 7),
                      imm(9, 0, 11, 9), imm(9, 0, 12, 4)], registers)
        self.assertTrue(result['completed'])
        self.assertEqual((result['gpr'][10], result['gpr'][11], result['gpr'][12]),
                         (7, 0, 4))
        self.assertEqual(result['visited_pcs'], (CODE, CODE + 4, CODE + 12))

    def test_not_taken_branch_executes_slot(self):
        regs = [0] * 32
        regs[8], regs[9] = 1, 2
        result = run([imm(4, 8, 9, 2), imm(9, 0, 10, 7),
                      imm(9, 0, 11, 9), imm(9, 0, 12, 4)], regs)
        self.assertTrue(result['completed'])
        self.assertEqual(result['visited_pcs'], (CODE, CODE + 4, CODE + 8, CODE + 12))

    def test_branch_likely_annuls_slot(self):
        regs = [0] * 32
        regs[8], regs[9] = 1, 2
        result = run([imm(20, 8, 9, 2), imm(9, 0, 10, 7),
                      imm(9, 0, 11, 9), 0], regs)
        self.assertTrue(result['completed'])
        self.assertEqual(result['gpr'][10], 0)
        self.assertEqual(result['gpr'][11], 9)
        self.assertEqual(result['visited_pcs'], (CODE, CODE + 8, CODE + 12))

    def test_load_delay_branch_predicate_precedes_commit(self):
        mem = Memory(0x1000, (5).to_bytes(4, 'little') + bytes(28))
        regs = [0] * 32
        regs[11] = 0x1000
        # Branch sees old r8=0, so BEQ r8,r9 is taken. Pending LW commits
        # after branch; its delay-slot instruction then reads new r8=5.
        result = run([imm(35, 11, 8, 0), imm(4, 8, 9, 2),
                      imm(9, 8, 10, 1), imm(9, 0, 10, 99),
                      imm(43, 11, 10, 4)], regs, mem)
        self.assertTrue(result['completed'])
        self.assertEqual(result['gpr'][10], 6)
        self.assertEqual(mem.read(0x1004, 4), 6)
        self.assertEqual(result['visited_pcs'],
                         (CODE, CODE + 4, CODE + 8, CODE + 16))

    def test_jump_delay_slot_and_return_stop(self):
        regs = [0] * 32
        regs[31] = CODE + 0x100
        result = run([jump(CODE + 16), imm(9, 0, 8, 12),
                      imm(9, 0, 8, 99), 0,
                      reg(8, rs=31), imm(9, 8, 9, 1)],
                     regs, stop_pc=CODE + 0x100)
        self.assertTrue(result['completed'])
        self.assertEqual(result['reason'], 'stop_pc')
        self.assertEqual((result['gpr'][8], result['gpr'][9]), (12, 13))

    def test_branch_in_delay_slot_rejected(self):
        result = run([jump(CODE + 12), imm(4, 0, 0, 0), 0, 0])
        self.assertFalse(result['completed'])
        self.assertEqual(result['reason'], 'ValueError')
        self.assertEqual(result['executed'], 1)

    def test_bounded_loop(self):
        result = run([jump(CODE), 0], max_steps=7)
        self.assertFalse(result['completed'])
        self.assertEqual((result['reason'], result['executed']), ('step_limit', 7))

    def test_original_layout_nine_stores_through_jump(self):
        mem = prepare_matrix_memory(synthetic_cardinal_table(), MATRIX)
        regs = [0] * 32
        regs[8] = TABLE_ADDRESS
        regs[5] = MATRIX
        # Sine=0 and cosine=4096 at synthetic angle 0. A branch skips a
        # deliberately invalid memory instruction; its delay slot stores
        # the first coefficient. Eight more SH instructions finish matrix.
        words = [imm(35, 8, 10, 0), 0,
                 reg(3, rt=10, rd=11, shift=16),
                 reg(0, rt=10, rd=12, shift=16),
                 reg(3, rt=12, rd=12, shift=16),
                 jump(CODE + 32),
                 imm(41, 5, 11, 0),
                 imm(35, 0, 9, 0),  # skipped LW at unmapped address
                 ]
        for offset in range(2, 18, 2):
            words.append(imm(41, 5, 11 if offset in (8, 16) else 12, offset))
        result = run(words, regs, mem)
        self.assertTrue(result['completed'])
        self.assertEqual(result['store_addresses'],
                         tuple(MATRIX + offset for offset in range(0, 18, 2)))
        self.assertEqual(matrix_coefficients(mem, MATRIX),
                         (4096, 0, 0, 0, 4096, 0, 0, 0, 4096))

    def test_unsupported_cop2_stops_without_guessing(self):
        result = run([18 << 26, 0])
        self.assertEqual((result['reason'], result['executed']), ('ValueError', 0))


if __name__ == '__main__':
    unittest.main()
