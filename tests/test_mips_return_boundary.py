"""Executed MIPS JR delay slot evidence, never static return-byte guesses."""
import struct
import unittest

from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_return_boundary import verify

BASE = 0x80010000
RAM = 0x80110000


def op(code, rs=0, rt=0, imm=0):
    return code << 26 | rs << 21 | rt << 16 | imm & 65535


def jr(rs=31):
    return (rs << 21) | 8


def run(words, *, regs=None, stop=None, max_steps=80):
    code = struct.pack('<%dI' % len(words), *words)
    memory = (MappedMemory().map_region(BASE, code)
              .map_region(RAM, struct.pack('<2I', 7, 9), writable=True))
    if regs is None:
        regs = [0] * 32
    if stop is None:
        stop = BASE + len(code)
    tr = execute(code, BASE, BASE, memory, regs,
                 stop_pc=stop, max_steps=max_steps)
    return tr, verify(tr, stop)


class ReturnBoundaryTests(unittest.TestCase):
    def test_jr_ra_return_requires_executed_delay_slot(self):
        regs = [0]*32
        regs[31] = BASE + 8
        tr, r = run([jr(), op(9,0,8,17)], regs=regs)
        self.assertEqual(tr['gpr'][8],17)
        self.assertTrue(r['verified_complete_jr_ra_return'])
        self.assertTrue(r['jr_ra_delay_slot_executed_last'])
        self.assertEqual(tr['control_transfers'],((BASE,'jr_ra',BASE+8),))

    def test_static_jr_without_slot_does_not_complete(self):
        regs = [0]*32
        regs[31] = BASE + 8
        tr, r = run([jr(),op(9,0,8,17)], regs=regs, max_steps=1)
        self.assertFalse(r['verified_complete_jr_ra_return'])
        self.assertFalse(r['last_completed_transfer_is_jr_ra_to_stop'])
        self.assertEqual(tr['reason'],'step_limit')

    def test_unsupported_delay_slot_does_not_complete_jr(self):
        regs = [0]*32
        regs[31] = BASE+8
        tr,r=run([jr(),18<<26],regs=regs)
        self.assertEqual(tr['reason'],'ValueError')
        self.assertFalse(r['last_completed_transfer_is_jr_ra_to_stop'])

    def test_jr_other_register_not_same_as_jr_ra(self):
        regs=[0]*32
        regs[8]=BASE+8
        _,r=run([jr(8),0],regs=regs)
        self.assertFalse(r['last_completed_transfer_is_jr_ra_to_stop'])

    def test_jalr_not_same_as_jr_ra(self):
        regs=[0]*32
        regs[8]=BASE+8
        jalr=(8<<21)|(30<<11)|9
        tr,r=run([jalr,0],regs=regs)
        self.assertTrue(tr['completed'])
        self.assertEqual(tr['gpr'][30],BASE+8)
        self.assertFalse(r['verified_complete_jr_ra_return'])

    def test_unconditional_jump_not_same_as_jr_ra(self):
        j=(2<<26)|(((BASE+8)>>2)&0x3ffffff)
        _,r=run([j,0])
        self.assertFalse(r['verified_complete_jr_ra_return'])

    def test_nonreturn_fallthrough_is_not_return(self):
        tr,r=run([op(9,0,8,4),0])
        self.assertTrue(tr['completed'])
        self.assertFalse(r['verified_complete_jr_ra_return'])

    def test_completed_jr_before_later_code_does_not_prove_last_return(self):
        regs=[0]*32
        regs[31]=BASE+16
        tr,r=run([jr(),0,0,0,op(9,0,8,3)],regs=regs)
        self.assertEqual(tr['visited_pcs'],(BASE,BASE+4,BASE+16))
        self.assertFalse(r['last_completed_transfer_is_jr_ra_to_stop'])
        self.assertFalse(r['jr_ra_delay_slot_executed_last'])

    def test_completed_jr_with_pending_load_at_return_rejected(self):
        regs=[0]*32
        regs[31],regs[5]=BASE+8,RAM
        tr,r=run([jr(),op(35,5,8,0)],regs=regs)
        self.assertTrue(tr['completed'])
        self.assertTrue(r['jr_ra_delay_slot_executed_last'])
        self.assertFalse(r['no_pending_delayed_load_at_stop'])
        self.assertFalse(r['verified_complete_jr_ra_return'])

    def test_prior_load_retired_by_delay_slot_accepted(self):
        regs=[0]*32
        regs[31],regs[5]=BASE+12,RAM
        tr,r=run([op(35,5,8,0),jr(),0],regs=regs)
        self.assertEqual(tr['gpr'][8],7)
        self.assertTrue(r['verified_complete_jr_ra_return'])

    def test_malformed_trace_is_rejected(self):
        for tr in (None, {}, {'visited_pcs':(), 'control_transfers':[(1,2)]},
                   {'visited_pcs':('invalid',), 'control_transfers':()}):
            with self.subTest(value=tr), self.assertRaises(ValueError):
                verify(tr,BASE+8)

    def test_invalid_expected_stop_rejected(self):
        with self.assertRaises(ValueError): verify({},BASE+1)
        with self.assertRaises(ValueError): verify({},True)

    def test_safe_output_contains_no_guest_addresses(self):
        regs=[0]*32
        regs[31]=BASE+8
        _,r=run([jr(),0],regs=regs)
        self.assertNotIn(hex(BASE),str(r))
        self.assertFalse(r['original_hardware_return_verified'])
        self.assertFalse(r['private_values_emitted'])


if __name__=='__main__': unittest.main()
