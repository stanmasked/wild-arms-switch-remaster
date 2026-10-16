"""Purely synthetic MIPS code and sparse test-only Q12 sine/cosine table."""
import struct
import unittest
from tools.mips_trig_index_provenance import summarize
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.audit_gp0_trig_table import TABLE
from tools.mips_trig_memory import synthetic_cardinal_table

BASE=0x80010000
STACK=0x80120000

def ins(op,rs=0,rt=0,imm=0):
    return (op << 26)|(rs << 21)|(rt << 16)|(imm & 0xffff)
def r(fn,rs=0,rt=0,rd=0,sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn

def trial(words, gpr=None, stack=None, max_steps=300):
    image=struct.pack('<%dI'%len(words),*words)
    mem=MappedMemory().map_region(BASE,image).map_region(TABLE,synthetic_cardinal_table())
    mem.map_region(STACK,bytes(64) if stack is None else stack)
    registers=[0]*32 if gpr is None else gpr
    trace=execute(image,BASE,BASE,mem,registers,max_steps=max_steps)
    profile=summarize(image,BASE,trace['visited_pcs'],trace['load_accesses'])
    return trace,profile

class TrigIndexProvenanceTests(unittest.TestCase):
    def test_lui_andi_sll_addu_lw_a0_dependency(self):
        words=[ins(12,4,8,0x0fff),r(0,rt=8,rd=8,sa=2),
               ins(15,0,9,0x800d),r(33,rs=9,rt=8,rd=9),
               ins(35,9,10,-0x41bc),0]
        regs=[0]*32;regs[4]=1024
        trace,report=trial(words,regs)
        self.assertTrue(trace['completed'])
        self.assertEqual(report['packed_table_loads_with_provenance'],1)
        self.assertEqual(report['address_dependency_gprs'],[4])
        self.assertEqual(report['address_dependency_lookup_counts'],[{'gpr':4,'lookup_count':1}])
        self.assertEqual(report['lookups_with_shift_left_two_in_address_chain'],1)
        self.assertEqual(report['lookups_with_12bit_mask_in_address_chain'],1)
        self.assertEqual(report['lookups_with_prior_memory_read_in_address_chain'],0)
        self.assertFalse(report['original_angle_values_recovered'])
        self.assertNotIn('index',str(report).lower().replace('angle_values',''))

    def test_lui_absolute_pointer_without_input_dependency(self):
        words=[ins(15,0,9,0x800d),ins(35,9,10,-0x41bc),0]
        trace,report=trial(words)
        self.assertTrue(trace['completed'])
        self.assertEqual(report['packed_table_loads_with_provenance'],1)
        self.assertEqual(report['lookups_with_no_external_address_dependencies'],1)
        self.assertEqual(report['address_dependency_gprs'],[])

    def test_seeded_absolute_table_pointer_is_gpr_dependency_not_angle_proof(self):
        regs=[0]*32;regs[8]=TABLE
        _,report=trial([ins(35,8,10,0),0],regs)
        self.assertEqual(report['address_dependency_gprs'],[8])
        self.assertFalse(report['input_gpr_proven_to_be_game_angle'])

    def test_memory_loaded_index_reaches_table_only_after_load_delay(self):
        words=[ins(35,29,4,0),0,ins(12,4,8,0xfff),
               r(0,rt=8,rd=8,sa=2),ins(15,0,9,0x800d),
               r(33,rs=9,rt=8,rd=9),ins(35,9,10,-0x41bc),0]
        regs=[0]*32;regs[29]=STACK
        memdata=bytearray(64);struct.pack_into('<I',memdata,0,1024)
        trace,report=trial(words,regs,memdata)
        self.assertTrue(trace['completed'])
        self.assertEqual(report['packed_table_loads_with_provenance'],1)
        self.assertEqual(report['lookups_with_prior_memory_read_in_address_chain'],1)
        self.assertEqual(report['address_dependency_gprs'],[29])

    def test_lw_delay_slot_immediate_use_is_old_register(self):
        words=[ins(35,29,4,0),r(0,rt=4,rd=8,sa=2),
               ins(15,0,9,0x800d),r(33,rs=9,rt=8,rd=9),
               ins(35,9,10,-0x41bc),0]
        regs=[0]*32;regs[29]=STACK;regs[4]=0
        memdata=bytearray(64);struct.pack_into('<I',memdata,0,1024)
        trace,report=trial(words,regs,memdata)
        self.assertTrue(trace['completed'])
        self.assertEqual(report['lookups_with_prior_memory_read_in_address_chain'],0)
        self.assertEqual(report['address_dependency_gprs'],[4])

    def test_previous_load_superseded_by_immediate_write(self):
        words=[ins(35,29,4,0),ins(9,0,4,0),
               r(0,rt=4,rd=8,sa=2),ins(15,0,9,0x800d),
               r(33,rs=9,rt=8,rd=9),ins(35,9,10,-0x41bc),0]
        regs=[0]*32;regs[29]=STACK
        trace,report=trial(words,regs)
        self.assertTrue(trace['completed'])
        self.assertEqual(report['address_dependency_gprs'],[])
        self.assertEqual(report['lookups_with_prior_memory_read_in_address_chain'],0)

    def test_missing_successful_read_event_rejected(self):
        image=struct.pack('<I',ins(35,8,9,0))
        with self.assertRaises(ValueError): summarize(image,BASE,(BASE,),())

    def test_unconsumed_load_event_rejected(self):
        with self.assertRaises(ValueError): summarize(struct.pack('<I',0),BASE,(BASE,),[(BASE,TABLE,4,9)])

    def test_repeated_load_at_same_pc_matches_event_order(self):
        # J loop; the same PC can appear more than once. All reads are real.
        regs=[0]*32;regs[8]=TABLE
        jump=(2<<26)|((BASE>>2)&0x3ffffff)
        trace,report=trial([ins(35,8,9,0),jump,0],regs,max_steps=8)
        self.assertEqual(trace['reason'],'step_limit')
        self.assertEqual(report['packed_table_loads_with_provenance'],3)
        self.assertEqual(report['address_dependency_lookup_counts'],[{'gpr':8,'lookup_count':3}])

    def test_non_table_load_unrelated_to_angle(self):
        regs=[0]*32;regs[8]=STACK
        _,report=trial([ins(35,8,9,0),0],regs)
        self.assertEqual(report['packed_table_loads_with_provenance'],0)
        self.assertEqual(report['address_dependency_gprs'],[])

    def test_invalid_pc_is_rejected(self):
        with self.assertRaises(ValueError): summarize(struct.pack('<I',0),BASE,(BASE+4,),[])

if __name__=='__main__': unittest.main()
