import struct
import unittest
from tools.mips_entry_dependencies import accesses, read_before_write

BASE = 0x80010000

def ins(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)

def r(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn

def deps(words, pcs=None):
    image = struct.pack('<%dI' % len(words), *words)
    if pcs is None:
        pcs = tuple(BASE + 4 * index for index in range(len(words)))
    return read_before_write(image, BASE, pcs)

class EntryDependenciesTests(unittest.TestCase):
    def test_caller_a1_comes_from_sp_and_jal_writes_ra(self):
        self.assertEqual(deps([ins(9,29,5,16), ins(3), r(8,rs=31), 0]), (29,))

    def test_builder_a0_angle_is_external(self):
        self.assertEqual(deps([r(0,rt=4,rd=8,sa=2), ins(41,5,8,0)]), (4,5))

    def test_lw_delay_reads_previous_register_value(self):
        self.assertEqual(deps([ins(35,8,9,0), ins(9,9,10,1),
                               ins(9,9,11,1)]), (8,9))

    def test_load_visible_after_nop(self):
        self.assertEqual(deps([ins(35,8,9,0),0,ins(9,9,10,1)]), (8,))

    def test_consecutive_load_same_destination(self):
        self.assertEqual(deps([ins(35,8,9,0),ins(35,8,9,4),
                               ins(9,9,10,1),ins(9,9,11,1)]), (8,))

    def test_branch_uses_source_before_delayed_load_commits(self):
        self.assertEqual(deps([ins(35,8,9,0),ins(4,9,0,1),0]),(8,9))

    def test_unvisited_branch_path_is_not_claimed(self):
        words=[ins(9,0,8,1),ins(9,6,7,1),ins(9,8,10,1)]
        self.assertEqual(deps(words,(BASE,BASE+8)),())

    def test_store_reads_source_and_base(self):
        self.assertEqual(deps([ins(43,5,10,4)]),(5,10))

    def test_hi_lo_moves_do_not_require_unknown_gpr(self):
        self.assertEqual(deps([r(18,rd=10),r(17,rs=10)]),())

    def test_invalid_pc_and_unknown_opcode_fail_closed(self):
        with self.assertRaises(ValueError): deps([0],(BASE+4,))
        with self.assertRaises(ValueError): deps([18<<26])

if __name__=='__main__': unittest.main()
