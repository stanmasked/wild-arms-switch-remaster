"""Synthetic R3000A one-instruction load-delay state at a debugger boundary."""
import struct
import unittest

from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory

CODE = 0x80010000
RAM = 0x80100000


def ins(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def replay(words, regs=None, *, initial=None, stop=None):
    raw = struct.pack('<%dI' % len(words), *words)
    memory = (MappedMemory().map_region(CODE, raw)
              .map_region(RAM, struct.pack('<4I', 17, 23, 29, 31), writable=True))
    registers = [0] * 32 if regs is None else regs
    trace = execute(raw, CODE, CODE, memory, registers,
                    initial_pending_load=initial, stop_pc=stop)
    return trace, memory


class InitialPipelineTests(unittest.TestCase):
    def test_initial_pending_load_is_not_visible_to_first_instruction(self):
        regs = [0] * 32
        regs[8] = 3
        words = [ins(9, 8, 9, 1), ins(9, 8, 10, 1)]
        trace, _ = replay(words, regs, initial=(8, 17))
        self.assertTrue(trace['completed'])
        self.assertEqual(trace['gpr'][9], 4)
        self.assertEqual(trace['gpr'][10], 18)
        self.assertEqual(trace['gpr'][8], 17)

    def test_first_instruction_store_uses_old_register_before_pending_load(self):
        regs = [0] * 32
        regs[5], regs[8] = RAM, 3
        tr, mem = replay([ins(41, 5, 8, 0), ins(41, 5, 8, 2)], regs, initial=(8, 17))
        self.assertTrue(tr['completed'])
        self.assertEqual(mem.read(RAM, 2), 3)
        self.assertEqual(mem.read(RAM+2, 2), 17)

    def test_initial_pending_load_followed_by_alu_overwrite_is_discarded(self):
        regs = [0] * 32
        words = [ins(9, 0, 8, 7), ins(9, 8, 9, 1)]
        trace, _ = replay(words, regs, initial=(8, 17))
        self.assertEqual(trace['gpr'][8], 7)
        self.assertEqual(trace['gpr'][9], 8)

    def test_branch_tests_old_gpr_and_delay_slot_tests_new_gpr(self):
        regs = [0] * 32
        regs[8] = 0
        # BEQ t0,$zero taken using old t0=0, slot sees new t0=17.
        code = [ins(4, 8, 0, 2), ins(9, 8, 9, 1),
                ins(9, 0, 9, 100), ins(9, 0, 10, 8)]
        trace, _ = replay(code, regs, initial=(8, 17))
        self.assertTrue(trace['completed'])
        self.assertEqual(trace['gpr'][9], 18)
        self.assertEqual(trace['visited_pcs'], (CODE, CODE+4, CODE+12))

    def test_branch_likely_annul_still_retires_prior_pending_load(self):
        regs = [0]*32
        regs[8] = 1
        code = [ins(20,8,0,1),ins(9,0,9,99),ins(9,8,10,1)]
        trace, _ = replay(code, regs, initial=(8, 17))
        self.assertTrue(trace['completed'])
        self.assertEqual(trace['gpr'][9], 0)
        self.assertEqual(trace['gpr'][10], 18)

    def test_back_to_back_lw_same_gpr_retires_earlier_load(self):
        regs = [0] * 32
        regs[5], regs[8] = RAM, 3
        code = [ins(35,5,8,0),ins(35,5,8,4),
                ins(9,8,9,1),ins(9,8,10,1)]
        tr, _ = replay(code,regs)
        self.assertTrue(tr['completed'])
        self.assertEqual(tr['gpr'][9],18)  # first load=17 is visible
        self.assertEqual(tr['gpr'][10],24) # second load=23 is visible
        self.assertEqual(tr['gpr'][8],23)

    def test_back_to_back_lw_same_gpr_at_capture_boundary(self):
        regs = [0]*32
        regs[5],regs[8] = RAM,3
        code = [ins(35,5,8,4),ins(9,8,9,1),ins(9,8,10,1)]
        tr,_=replay(code,regs,initial=(8,17))
        self.assertTrue(tr['completed'])
        self.assertEqual(tr['gpr'][9],18)
        self.assertEqual(tr['gpr'][10],24)

    def test_one_instruction_stop_preserves_pending_load_if_not_executed(self):
        tr,_ = replay([0],initial=(8,17),stop=CODE)
        self.assertEqual(tr['reason'],'stop_pc')
        self.assertEqual(tr['executed'],0)
        self.assertEqual(tr['pending_load'],(8,17))

    def test_one_instruction_nop_retires_initial_pending_load(self):
        tr,_=replay([0],initial=(8,17))
        self.assertEqual(tr['gpr'][8],17)
        self.assertIsNone(tr['pending_load'])

    def test_zero_gpr_remains_zero(self):
        tr,_=replay([0],initial=(1,0xffffffff))
        self.assertEqual(tr['gpr'][0],0)
        self.assertEqual(tr['gpr'][1],0xffffffff)

    def test_invalid_initial_pending_load_fails_before_replay(self):
        bad = [(0, 17), (32, 1),(-1,1), (True,1),(8,True),
               (8,-1),(8,0x100000000), (8,), '8,17', (8,1,2)]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):
                replay([0],initial=value)

    def test_none_preserves_original_default_behaviour(self):
        normal,_=replay([ins(9,0,8,17),0])
        explicit,_=replay([ins(9,0,8,17),0],initial=None)
        self.assertEqual(normal['gpr'],explicit['gpr'])
        self.assertEqual(normal['visited_pcs'],explicit['visited_pcs'])

if __name__=='__main__':unittest.main()
