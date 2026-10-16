import struct
import unittest
from tools.mips_call_boundary import analyze_boundary, available_after_path

BASE=0x80010000

def ins(op,rs=0,rt=0,imm=0):
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)

def spec(fn,rs=0,rt=0,rd=0,sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn

def audit(words, start):
    image=struct.pack('<%dI'%len(words),*words)
    pcs=tuple(BASE+4*i for i in range(len(words)))
    return analyze_boundary(image,BASE,pcs,BASE+4*start)

class CallBoundaryTests(unittest.TestCase):
    def test_sp_prepares_a1_and_jal_prepares_ra(self):
        words=[ins(9,29,5,16),ins(3),0, ins(41,5,4,0),spec(8,rs=31),0]
        r=audit(words,3)
        self.assertEqual(r['builder_read_before_write_gprs'],[4,5,31])
        self.assertEqual(r['builder_inputs_prepared_by_caller'],[5,31])
        self.assertEqual(r['builder_inputs_unresolved'],[4])

    def test_caller_also_prepares_a0(self):
        words=[ins(9,0,4,16),ins(9,29,5,16),ins(3),0,
               ins(41,5,4,0),spec(8,rs=31),0]
        r=audit(words,4)
        self.assertEqual(r['builder_inputs_unresolved'],[])
        self.assertEqual(r['builder_inputs_prepared_by_caller'],[4,5,31])

    def test_callee_own_write_satisfies_later_use(self):
        words=[ins(9,29,5,16),ins(3),0, ins(9,0,6,7), ins(41,5,6,0)]
        r=audit(words,3)
        self.assertEqual(r['builder_read_before_write_gprs'],[5])
        self.assertEqual(r['builder_inputs_prepared_by_caller'],[5])

    def test_caller_delay_slot_load_is_pending_on_entry(self):
        words=[ins(3),ins(35,8,4,0), ins(41,5,4,0),0]
        r=audit(words,2)
        self.assertEqual(r['pending_load_at_entry_gpr'],4)
        self.assertEqual(r['builder_inputs_unresolved'],[4,5])
        self.assertEqual(r['builder_inputs_prepared_by_caller'],[])

    def test_pending_load_commits_after_nop(self):
        words=[ins(35,8,4,0),0,ins(3),0,ins(41,5,4,0)]
        r=audit(words,4)
        self.assertEqual(r['pending_load_at_entry_gpr'],None)
        self.assertEqual(r['builder_inputs_prepared_by_caller'],[4])

    def test_caller_write_cancels_pending_load(self):
        words=[ins(35,8,4,0),ins(9,0,4,10),ins(3),0,ins(41,5,4,0)]
        r=audit(words,4)
        self.assertEqual(r['pending_load_at_entry_gpr'],None)
        self.assertEqual(r['builder_inputs_prepared_by_caller'],[4])

    def test_missing_entry_explicit_not_false_inference(self):
        r=analyze_boundary(b'\0'*8,BASE,(BASE,BASE+4),BASE+12)
        self.assertFalse(r['builder_entry_reached'])
        self.assertEqual(r['builder_inputs_unresolved'],[])

    def test_reject_invalid_visited_pc(self):
        with self.assertRaises(ValueError):
            available_after_path(b'\0'*4, BASE, (BASE+8,))

    def test_nonvisited_caller_branch_is_ignored(self):
        words=[ins(9,29,5,16), ins(9,0,4,0), ins(3), 0,ins(41,5,4,0)]
        image=struct.pack('<%dI'%len(words),*words)
        visited=(BASE,BASE+8,BASE+12,BASE+16)
        r=analyze_boundary(image,BASE,visited,BASE+16)
        self.assertEqual(r['builder_inputs_unresolved'],[4])

if __name__=='__main__':unittest.main()
