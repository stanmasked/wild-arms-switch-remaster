"""Synthetic concrete control/guest memory facts, never original game state."""
import struct
import unittest
from tools.mips_builder_execution_evidence import summarize
from tools.mips_matrix_operation_schedule import summarize as schedules
from tools.mips_matrix_value_lineage import summarize as lineage
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_q12_differential import build_nine_product_program, build_nine_dot3_program
from tools.mips_trig_memory import synthetic_cardinal_table
from tools.audit_gp0_trig_table import TABLE

BASE = 0x80010000
MATRIX = 0x80100200
LEFT = 0x80100000
RIGHT = 0x80100100

def ins(op,rs=0,rt=0,imm=0):
    return op<<26 | rs<<21 | rt<<16 | (imm & 65535)

def run(words, *, start=BASE, end=None, seed=0, max_steps=None, extra_regs=None,
        known_lookup_pcs=()):
    image=struct.pack('<%dI' % len(words),*words)
    mem=(MappedMemory().map_region(BASE,image)
         .map_region(MATRIX,bytes(18),writable=True)
         .map_region(LEFT,struct.pack('<27H',*([seed]*27)))
         .map_region(RIGHT,struct.pack('<27H',*([seed]*27)))
         .map_region(TABLE,synthetic_cardinal_table()))
    gpr=[0]*32
    gpr[5]=MATRIX;gpr[16]=LEFT;gpr[17]=RIGHT
    for reg,value in (extra_regs or {}).items():gpr[reg]=value
    trace=execute(image,BASE,BASE,mem,gpr,max_steps=max_steps or len(words)+5)
    if end is None:end=BASE+(len(words)-1)*4
    report=summarize(image,BASE,start,end,trace,MATRIX,
                     operation_schedule=schedules(image,BASE,trace,MATRIX),
                     value_lineage=lineage(image,BASE,trace,MATRIX),
                     known_lookup_pcs=known_lookup_pcs)
    return trace,report

class BuilderExecutionEvidenceTests(unittest.TestCase):
    def test_nine_static_and_executed_sh_sites_agree(self):
        trace,r=run(build_nine_product_program()+(0,))
        self.assertTrue(trace['completed'])
        self.assertEqual(r['static_matrix_sh_syntax_site_count'],9)
        self.assertEqual(r['static_matrix_sh_syntax_sites_executed'],9)
        self.assertEqual(r['static_matrix_sh_syntax_sites_not_executed'],0)
        self.assertEqual(r['final_matrix_slots_verified_against_static_sh_site'],9)
        self.assertEqual(r['final_verified_slots_with_recognized_arithmetic_schedule'],9)
        self.assertTrue(all(x['final_sh_matches_static_a1_offset'] for x in r['matrix_slots']))
        self.assertFalse(r['original_builder_reachability_proven'])

    def test_both_dot3_arithmetic_orders_attested(self):
        for shift,expected in ((False,'shift_after_three_products'),
                               (True,'shift_each_of_three_products')):
            with self.subTest(shift_each=shift):
                _,r=run(build_nine_dot3_program(shift_each=shift)+(0,))
                self.assertEqual(r['final_verified_slots_with_recognized_arithmetic_schedule'],9)
                self.assertTrue(all(x['observed_arithmetic_schedule']==expected
                                    for x in r['matrix_slots']))

    def test_statically_present_but_skipped_sh_not_counted_as_executed(self):
        jump = (2<<26) | (((BASE+20)>>2)&0x3ffffff)
        words=(jump,0,ins(41,5,8,0),0,0,ins(41,5,8,2),0)
        trace,r=run(words)
        self.assertTrue(trace['completed'])
        self.assertEqual(r['static_matrix_sh_syntax_site_count'],2)
        self.assertEqual(r['static_matrix_sh_syntax_sites_executed'],1)
        self.assertEqual(r['static_matrix_sh_syntax_sites_not_executed'],1)
        self.assertEqual(r['final_matrix_slots_verified_against_static_sh_site'],1)
        self.assertFalse(r['matrix_slots'][0]['final_successful_sh_observed'])
        self.assertTrue(r['matrix_slots'][1]['final_sh_matches_static_a1_offset'])

    def test_sh_in_caller_before_builder_entry_is_not_original_site_evidence(self):
        words=(ins(41,5,8,0),0,0)
        _,r=run(words,start=BASE+4)
        self.assertTrue(r['matrix_slots'][0]['final_successful_sh_observed'])
        self.assertFalse(r['matrix_slots'][0]['final_sh_matches_static_a1_offset'])
        self.assertEqual(r['static_matrix_sh_syntax_site_count'],0)

    def test_wrong_base_register_can_hit_matrix_but_not_static_a1_syntax(self):
        words=(ins(41,9,8,0),0)
        _,r=run(words,extra_regs={9:MATRIX})
        self.assertTrue(r['matrix_slots'][0]['final_successful_sh_observed'])
        self.assertFalse(r['matrix_slots'][0]['final_sh_matches_static_a1_offset'])

    def test_static_a1_sh_with_wrong_resolved_address_is_not_verified(self):
        words=(ins(41,5,8,0),0)
        # Setting a1 to a mapped buffer other than MATRIX is fine.
        # LEFT is read-only, so use an overlapping mapped (writable) region?
        # We instead use MATRIX+2 and SH lands at slot 1, not encoded slot 0.
        _,r=run(words,extra_regs={5:MATRIX+2})
        self.assertTrue(r['matrix_slots'][1]['final_successful_sh_observed'])
        self.assertFalse(r['matrix_slots'][1]['final_sh_matches_static_a1_offset'])

    def test_later_sw_revokes_successful_static_sh(self):
        words=(ins(41,5,8,0),ins(43,5,8,0),0)
        _,r=run(words)
        self.assertEqual(r['static_matrix_sh_syntax_sites_executed'],1)
        self.assertFalse(r['matrix_slots'][0]['final_successful_sh_observed'])
        self.assertEqual(r['final_matrix_slots_verified_against_static_sh_site'],0)

    def test_later_sb_only_revokes_overlapped_halfword(self):
        words=(ins(41,5,8,0),ins(41,5,8,2),ins(40,5,8,1),0)
        _,r=run(words)
        self.assertFalse(r['matrix_slots'][0]['final_successful_sh_observed'])
        self.assertTrue(r['matrix_slots'][1]['final_sh_matches_static_a1_offset'])

    def test_known_lookup_instruction_must_really_read_table(self):
        words=(ins(35,8,9,0),0)
        _,r=run(words,extra_regs={8:TABLE},known_lookup_pcs=(BASE,))
        self.assertEqual(r['known_trig_lw_sites_executed'],1)
        self.assertEqual(r['known_trig_lw_sites_with_verified_packed_reads'],1)
        self.assertEqual(r['successful_packed_table_load_events_in_trace'],1)

    def test_known_lookup_site_with_other_address_not_table(self):
        words=(ins(35,8,9,0),0)
        _,r=run(words,extra_regs={8:LEFT},known_lookup_pcs=(BASE,))
        self.assertEqual(r['known_trig_lw_sites_executed'],1)
        self.assertEqual(r['known_trig_lw_sites_with_verified_packed_reads'],0)
        self.assertEqual(r['successful_packed_table_load_events_in_trace'],0)

    def test_jr_ra_delay_slot_sh_confirmed_after_return_transfer(self):
        words=((31<<21)|8,ins(41,5,8,0),0)
        trace,r=run(words,end=BASE,extra_regs={31:BASE+12})
        self.assertTrue(trace['completed'])
        self.assertTrue(r['jr_ra_return_transfer_completed'])
        self.assertEqual(r['static_matrix_sh_syntax_site_count'],1)
        self.assertTrue(r['matrix_slots'][0]['final_sh_from_verified_return_delay_slot'])
        self.assertTrue(r['matrix_slots'][0]['final_sh_matches_static_a1_offset'])

    def test_nonreturn_end_does_not_claim_following_sh_as_delay_slot(self):
        words=(0,ins(41,5,8,0),0)
        trace,r=run(words,end=BASE)
        self.assertTrue(trace['completed'])
        self.assertFalse(r['jr_ra_return_transfer_completed'])
        self.assertEqual(r['static_matrix_sh_syntax_site_count'],0)
        self.assertTrue(r['matrix_slots'][0]['final_successful_sh_observed'])
        self.assertFalse(r['matrix_slots'][0]['final_sh_matches_static_a1_offset'])

    def test_annulled_branch_likely_sh_not_conflated_with_executed(self):
        words=(ins(20,4,0,1),ins(41,5,8,0),0,0)
        trace,r=run(words,extra_regs={4:1})
        self.assertTrue(trace['completed'])
        self.assertEqual(r['static_matrix_sh_syntax_site_count'],1)
        self.assertEqual(r['static_matrix_sh_syntax_sites_not_executed'],1)
        self.assertFalse(r['matrix_slots'][0]['final_successful_sh_observed'])

    def test_missing_load_event_rejected(self):
        words=(ins(35,8,9,0),0)
        image=struct.pack('<2I',*words)
        m=(MappedMemory().map_region(BASE,image)
           .map_region(TABLE,synthetic_cardinal_table()))
        gpr=[0]*32;gpr[8]=TABLE
        tr=execute(image,BASE,BASE,m,gpr)
        sch=schedules(image,BASE,tr,MATRIX)
        val=lineage(image,BASE,tr,MATRIX)
        with self.assertRaises(ValueError):
            summarize(image,BASE,BASE,BASE+4,{**tr,'load_accesses':()},MATRIX,
                      operation_schedule=sch,value_lineage=val)

    def test_extra_store_event_rejected(self):
        image=struct.pack('<I',0)
        m=MappedMemory().map_region(BASE,image)
        tr=execute(image,BASE,BASE,m)
        sch=schedules(image,BASE,tr,MATRIX)
        val=lineage(image,BASE,tr,MATRIX)
        with self.assertRaises(ValueError):
            summarize(image,BASE,BASE,BASE,{**tr,'store_addresses':(MATRIX,)},MATRIX,
                      operation_schedule=sch,value_lineage=val)

    def test_inconsistent_shadow_slot_report_rejected(self):
        image=struct.pack('<I',0)
        m=MappedMemory().map_region(BASE,image)
        tr=execute(image,BASE,BASE,m)
        sch=schedules(image,BASE,tr,MATRIX)
        val=lineage(image,BASE,tr,MATRIX)
        sch['matrix_slots'][0]['schedule']='unclassified'
        with self.assertRaises(ValueError):
            summarize(image,BASE,BASE,BASE,tr,MATRIX,
                      operation_schedule=sch,value_lineage=val)

    def test_stop_pc_before_store_does_not_assert_execution(self):
        words=(ins(41,5,8,0),0)
        image=struct.pack('<2I',*words)
        memory=MappedMemory().map_region(BASE,image).map_region(MATRIX,bytes(18),True)
        gpr=[0]*32;gpr[5]=MATRIX
        tr=execute(image,BASE,BASE,memory,gpr,stop_pc=BASE)
        rep=summarize(image,BASE,BASE,BASE+4,tr,MATRIX,
                      operation_schedule=schedules(image,BASE,tr,MATRIX),
                      value_lineage=lineage(image,BASE,tr,MATRIX))
        self.assertEqual(rep['static_matrix_sh_syntax_site_count'],1)
        self.assertEqual(rep['static_matrix_sh_syntax_sites_executed'],0)
        self.assertEqual(rep['final_matrix_slots_verified_against_static_sh_site'],0)

    def test_bad_range_rejected(self):
        words=(0,0)
        image=struct.pack('<2I',*words)
        tr={'visited_pcs':(), 'load_accesses':(), 'store_addresses':(),
            'control_transfers':(), 'completed':False}
        dummy_slots={'matrix_slots':[{'slot_index':i,'schedule':'not_written'} for i in range(9)]}
        dummy_vals={'matrix_slots':[{'slot_index':i,'written_by_sh':False} for i in range(9)]}
        with self.assertRaises(ValueError):
            summarize(image,BASE,BASE,BASE+8,tr,MATRIX,
                      operation_schedule=dummy_slots,value_lineage=dummy_vals)

    def test_static_summary_never_exposes_guest_values(self):
        _,r=run(build_nine_product_program()+(0,),seed=0xffff)
        self.assertFalse(r['private_values_emitted'])
        self.assertFalse(r['original_gameplay_coefficients_checked'])
        self.assertNotIn('0x801',str(r))
        self.assertNotIn('coefficient_values',r)

if __name__=='__main__':unittest.main()
