import struct
import unittest
from tools.mips_caller_sources import inspect

BASE=0x80010000

def imm(op,rs=0,rt=0,n=0):
    return (op<<26)|(rs<<21)|(rt<<16)|(n&65535)

def reg(fn,rs=0,rt=0,rd=0,sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn

def audit(before,slot=0,args=(4,5,6,7)):
    code=struct.pack('<%dI'%(len(before)+2),*(before+[(3<<26),slot]))
    return inspect(code,BASE,BASE+4*len(before),len(before),args)

class CallerSourceTests(unittest.TestCase):
    def test_existing_caller_pointer_from_sp(self):
        r=audit([imm(9,29,5,16),0,0,0])
        d={x['gpr']:x for x in r['arguments']}
        self.assertTrue(r['window_usable'])
        self.assertEqual(d[5]['source_kind'],'stack_pointer_derived')
        self.assertEqual(d[5]['incoming_gprs'],[29])
        self.assertEqual(d[4]['source_kind'],'incoming_gpr')
        self.assertFalse(r['runtime_path_confirmed'])
    def test_lui_constant(self):
        r=audit([imm(15,0,4,0x800c)])
        self.assertEqual(r['arguments'][0]['source_kind'],'literal_derived')
        self.assertEqual(r['arguments'][0]['incoming_gprs'],[])
    def test_arithmetic_from_a2(self):
        r=audit([imm(9,6,4,3)])
        self.assertEqual(r['arguments'][0]['source_kind'],'computed_gprs')
        self.assertEqual(r['arguments'][0]['incoming_gprs'],[6])
    def test_lui_ori_forms_literal_pointer(self):
        r=audit([imm(15,0,8,0x800c),imm(13,8,4,0xbe44)])
        self.assertEqual(r['arguments'][0]['source_kind'],'literal_derived')
        self.assertEqual(r['arguments'][0]['incoming_gprs'],[])
    def test_sltu_of_literal_registers_stays_literal(self):
        r=audit([imm(9,0,8,10),imm(9,0,9,11),reg(43,8,9,4)])
        self.assertEqual(r['arguments'][0]['source_kind'],'literal_derived')
    def test_variable_shift_tracks_two_sources(self):
        r=audit([reg(4,rs=6,rt=7,rd=4)])
        self.assertEqual(r['arguments'][0]['incoming_gprs'],[6,7])
    def test_negative_sp_adjustment_keeps_stack_provenance(self):
        r=audit([imm(9,29,8,-32),imm(35,8,4,12),0])
        self.assertEqual(r['arguments'][0]['memory_kinds'],['stack_load'])
    def test_stack_load(self):
        r=audit([imm(9,29,8,16),imm(35,8,4,0),0])
        d=r['arguments'][0]
        self.assertEqual(d['source_kind'],'memory_derived')
        self.assertEqual(d['memory_kinds'],['stack_load'])
        self.assertEqual(d['incoming_gprs'],[29])
    def test_absolute_load(self):
        r=audit([imm(15,0,8,0x800c),imm(35,8,4,0),0])
        self.assertEqual(r['arguments'][0]['memory_kinds'],['absolute_load'])
    def test_indirect_load(self):
        r=audit([imm(35,8,4,0),0])
        self.assertEqual(r['arguments'][0]['memory_kinds'],['indirect_load'])
        self.assertEqual(r['arguments'][0]['incoming_gprs'],[8])
    def test_load_delay_reads_old_arg_in_next_instruction(self):
        r=audit([imm(35,8,4,0),imm(9,4,6,1)])
        d={x['gpr']:x for x in r['arguments']}
        self.assertEqual(d[6]['incoming_gprs'],[4])
        self.assertEqual(d[4]['memory_kinds'],['indirect_load'])
    def test_load_in_jal_slot_is_still_pending(self):
        r=audit([0],imm(35,8,4,0))
        d=r['arguments'][0]
        self.assertTrue(d['load_pending_at_boundary'])
        self.assertEqual(d['source_kind'],'incoming_gpr')
    def test_load_in_jal_slot_leaves_earlier_load_visible(self):
        r=audit([imm(35,8,4,0)],imm(35,8,4,4))
        self.assertTrue(r['arguments'][0]['load_pending_at_boundary'])
        self.assertEqual(r['arguments'][0]['source_kind'],'memory_derived')
    def test_jal_slot_addiu_produces_a0(self):
        r=audit([0],imm(9,0,4,5))
        self.assertEqual(r['arguments'][0]['source_kind'],'literal_derived')
    def test_load_followed_by_write_cancels_load(self):
        r=audit([imm(35,8,4,0)],imm(9,0,4,5))
        self.assertEqual(r['arguments'][0]['source_kind'],'literal_derived')
        self.assertFalse(r['arguments'][0]['load_pending_at_boundary'])
    def test_midwindow_branch_rejected(self):
        r=audit([imm(4,0,0,1),0])
        self.assertFalse(r['window_usable'])
        self.assertEqual(r['reason'],'unsupported_window_instruction')
        self.assertEqual(r['arguments'],[])
    def test_unhandled_cop_rejected(self):
        r=audit([imm(18),0])
        self.assertFalse(r['window_usable'])
    def test_not_jal_rejected(self):
        data=struct.pack('<3I',0,0,0)
        r=inspect(data,BASE,BASE+4,1)
        self.assertEqual(r['reason'],'invalid_call')
    def test_short_window_rejected(self):
        data=struct.pack('<2I',0,0)
        self.assertFalse(inspect(data,BASE,BASE+4,2)['window_usable'])
    def test_shift_incoming_a0(self):
        r=audit([reg(0,rt=4,rd=6,sa=2)])
        self.assertEqual(r['arguments'][2]['incoming_gprs'],[4])
    def test_synthetic_mult_mflo(self):
        r=audit([reg(24,rs=4,rt=6),reg(18,rd=7)])
        self.assertEqual(r['arguments'][3]['incoming_gprs'],[4,6])

if __name__=='__main__': unittest.main()
