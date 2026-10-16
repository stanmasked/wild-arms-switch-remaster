"""All fixtures synthetic; never use original game table bytes."""
import unittest
import struct
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_load_access_profile import summarize
from tools.audit_gp0_trig_table import TABLE, TABLE_LOAD_PCS
from tools.mips_trig_memory import synthetic_cardinal_table

BASE = 0x80010000
STACK = 0x80120000
MATRIX = STACK + 0x100

def op(code, rs=0, rt=0, imm=0):
    return (code << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff)

def run(words, regs=None, stack=bytes(1024)):
    if regs is None: regs=[0]*32
    image=struct.pack('<%dI'%len(words),*words)
    memory=(MappedMemory().map_region(BASE,image,False)
            .map_region(TABLE,synthetic_cardinal_table(),False)
            .map_region(STACK,stack,True))
    trace=execute(image,BASE,BASE,memory,regs)
    report=summarize(trace['load_accesses'],image_base=BASE,image_size=len(image),
                     stack_base=STACK,stack_size=len(stack),matrix_address=MATRIX)
    return trace,report

class MIPSLoadAccessProfileTests(unittest.TestCase):
    def test_synthetic_table_lw_counts_without_values(self):
        regs=[0]*32;regs[8]=TABLE
        trace,result=run([op(35,8,9,0),0],regs)
        self.assertTrue(trace['completed'])
        self.assertEqual(result['successful_load_count'],1)
        self.assertEqual(result['read_groups']['packed_trig_lw'],1)
        self.assertEqual(result['distinct_packed_trig_entries'],1)
        self.assertFalse(result['original_rotation_angles_recovered'])
        self.assertNotIn('address',str(result))

    def test_repeated_same_table_index_not_double_counted_unique(self):
        regs=[0]*32;regs[8]=TABLE
        _,result=run([op(35,8,9,0),op(35,8,10,0),0],regs)
        self.assertEqual(result['read_groups']['packed_trig_lw'],2)
        self.assertEqual(result['distinct_packed_trig_entries'],1)

    def test_two_cardinal_indices_distinct(self):
        regs=[0]*32;regs[8]=TABLE;regs[9]=TABLE+4096
        _,result=run([op(35,8,10,0),0,op(35,9,11,0),0],regs)
        self.assertEqual(result['distinct_packed_trig_entries'],2)

    def test_partial_table_reads_not_counted_as_entries(self):
        regs=[0]*32;regs[8]=TABLE
        _,result=run([op(33,8,9,2),0],regs)
        self.assertEqual(result['read_groups']['partial_trig_read'],1)
        self.assertEqual(result['distinct_packed_trig_entries'],0)

    def test_stack_and_matrix_read_separately(self):
        regs=[0]*32;regs[8]=STACK;regs[9]=MATRIX
        _,result=run([op(35,8,10,0),0,op(33,9,11,0),0],regs)
        self.assertEqual(result['read_groups']['scratch_stack_read'],1)
        self.assertEqual(result['read_groups']['matrix_buffer_read'],1)

    def test_failed_load_not_recorded(self):
        regs=[0]*32;regs[8]=0x4000
        trace,result=run([op(35,8,9,0),0],regs)
        self.assertFalse(trace['completed'])
        self.assertEqual(result['successful_load_count'],0)
        self.assertEqual(trace['load_accesses'],())

    def test_annulled_delay_slot_load_not_recorded(self):
        regs=[0]*32;regs[8]=TABLE;regs[9]=1
        trace,result=run([op(20,0,9,1),op(35,8,10,0),0],regs)
        self.assertTrue(trace['completed'])
        self.assertEqual(result['successful_load_count'],0)

    def test_jr_delay_slot_load_counted(self):
        regs=[0]*32;regs[8]=TABLE;regs[31]=BASE+0x80
        word=(31<<21)|8
        image=struct.pack('<2I',word,op(35,8,9,0))
        mem=(MappedMemory().map_region(BASE,image)
             .map_region(TABLE,synthetic_cardinal_table()))
        trace=execute(image,BASE,BASE,mem,regs,stop_pc=BASE+0x80)
        self.assertTrue(trace['completed'])
        self.assertEqual(trace['load_accesses'],((BASE+4,TABLE,4,9),))

    def test_known_pc_does_not_imply_table_address(self):
        summary=summarize([(TABLE_LOAD_PCS[0],STACK,4,9)],
                    image_base=BASE,image_size=8,stack_base=STACK,
                    stack_size=1024,matrix_address=MATRIX)
        self.assertEqual(summary['known_lookup_sites_with_packed_reads'],0)
        self.assertEqual(summary['read_groups']['scratch_stack_read'],1)

    def test_actual_known_pc_and_table_address_both_required(self):
        summary=summarize([(TABLE_LOAD_PCS[0],TABLE,4,9)],
                    image_base=BASE,image_size=8,stack_base=STACK,
                    stack_size=1024,matrix_address=MATRIX)
        self.assertEqual(summary['known_lookup_sites_with_packed_reads'],1)

    def test_outside_address_is_generic_other(self):
        summary=summarize([(BASE,0x5000,4,9)],
                    image_base=BASE,image_size=8,stack_base=STACK,
                    stack_size=1024,matrix_address=MATRIX)
        self.assertEqual(summary['read_groups']['other_mapped_read'],1)

    def test_bad_read_event_fails_closed(self):
        for events in ([(BASE,TABLE+1,4,9)],[(BASE,TABLE,3,9)],
                       [(BASE,TABLE,4,32)],[(BASE,TABLE,4)]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                summarize(events,image_base=BASE,image_size=8,stack_base=STACK,
                          stack_size=1024,matrix_address=MATRIX)

if __name__=='__main__': unittest.main()
