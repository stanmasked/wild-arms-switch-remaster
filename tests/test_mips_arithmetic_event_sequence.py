"""Independent synthetic MIPS intermediate arithmetic outcome reference tests."""
import struct
import unittest
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_arithmetic_event_sequence import (
    SCHEMA, MAX_MISMATCH_INDICES, decode, compare, trace_events, instruction_kind)

BASE = 0x80010000
RAM = 0x80110000

def r(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn

def i(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff)

def replay(words, *, initial=None, regs=None, max_steps=100):
    image = struct.pack('<%dI' % len(words), *words)
    memory = MappedMemory().map_region(BASE, image).map_region(RAM, bytes(64), writable=True)
    state = list(regs) if regs is not None else [0] * 32
    return execute(image, BASE, BASE, memory, state,
                   initial_pending_load=initial, max_steps=max_steps), memory

def ref(*events):
    return decode({'schema': SCHEMA, 'events': [
        {'pc': pc, 'kind': kind, 'result_u32': result, 'secondary_u32': aux}
        for pc, kind, result, aux in events]})

class ArithmeticTraceTests(unittest.TestCase):
    def test_signed_multiply_mflo_sra_addu_exact_intermediate_values(self):
        regs = [0] * 32
        regs[8], regs[9], regs[13] = 1024, 2048, 7
        program = [r(24, 8, 9), r(18, rd=10), r(3, rt=10, rd=11, sa=12),
                   r(33, rs=11, rt=13, rd=12)]
        trace, _ = replay(program, regs=regs)
        oracle = ref((BASE, 'mult', 0x00200000, 0),
                     (BASE+4, 'mflo', 0x00200000, None),
                     (BASE+8, 'sra', 512, None),
                     (BASE+12, 'addu', 519, None))
        self.assertTrue(trace['completed'])
        self.assertTrue(compare(trace, oracle, guest_stopped_at_expected_pc=True)['matches_reference'])
        self.assertEqual(trace['gpr'][12], 519)

    def test_signed_negative_product_preserves_two_complement(self):
        regs=[0]*32; regs[8]=0xfffff000;regs[9]=4096
        words=[r(24,8,9),r(16,rd=10),r(18,rd=11),r(3,rt=11,rd=12,sa=12)]
        tr,_=replay(words,regs=regs)
        expected=ref((BASE,'mult',0xff000000,0xffffffff),
                     (BASE+4,'mfhi',0xffffffff,None),
                     (BASE+8,'mflo',0xff000000,None),
                     (BASE+12,'sra',0xfffff000,None))
        self.assertTrue(compare(tr,expected,guest_stopped_at_expected_pc=True)['matches_reference'])

    def test_unsigned_multiply_is_not_conflated_with_signed(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        tr,_=replay([r(25,8,9),r(16,rd=10),r(18,rd=11)],regs=regs)
        expected=ref((BASE,'multu',0xfffffffe,1),
                     (BASE+4,'mfhi',1,None),(BASE+8,'mflo',0xfffffffe,None))
        self.assertTrue(compare(tr,expected,guest_stopped_at_expected_pc=True)['matches_reference'])

    def test_shift_variable_srav_traces_observed_signed_result(self):
        regs=[0]*32;regs[8]=0x80000000;regs[9]=12
        tr,_=replay([r(7,rs=9,rt=8,rd=10)],regs=regs)
        self.assertTrue(compare(tr,ref((BASE,'srav',0xfff80000,None)),guest_stopped_at_expected_pc=True)['matches_reference'])

    def test_addu_overflow_wraps(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=3
        tr,_=replay([r(33,rs=8,rt=9,rd=10)],regs=regs)
        self.assertTrue(compare(tr,ref((BASE,'addu',2,None)),guest_stopped_at_expected_pc=True)['matches_reference'])

    def test_add_trapping_overflow_does_not_emit_false_event(self):
        regs=[0]*32;regs[8]=0x7fffffff;regs[9]=1
        tr,_=replay([r(32,rs=8,rt=9,rd=10)],regs=regs)
        self.assertFalse(tr['completed'])
        self.assertEqual(tr['arithmetic_accesses'],())

    def test_immediate_alu_and_nop_not_falsely_recorded(self):
        tr,_=replay([i(9,0,8,1),0])
        self.assertEqual(tr['arithmetic_accesses'],())

    def test_rd_zero_records_architectural_zero(self):
        regs=[0]*32;regs[8]=512;regs[9]=1024
        tr,_=replay([r(33,rs=8,rt=9,rd=0)],regs=regs)
        self.assertEqual(tr['arithmetic_accesses'][0][2],0)

    def test_prior_pending_lw_result_does_not_replace_alu_output(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10),r(33,rs=10,rt=9,rd=11)],
                    regs=regs,initial=(8,100))
        self.assertEqual(tr['arithmetic_accesses'][0],(BASE,'addu',11,None))
        self.assertEqual(tr['arithmetic_accesses'][1],(BASE+4,'addu',18,None))

    def test_return_delay_slot_arithmetic_is_logged(self):
        regs=[0]*32;regs[31]=BASE+8;regs[8]=4;regs[9]=7
        tr,_=replay([r(8,rs=31),r(33,rs=8,rt=9,rd=10)],regs=regs)
        self.assertTrue(tr['completed'])
        self.assertEqual(tr['arithmetic_accesses'],((BASE+4,'addu',11,None),))

    def test_differing_opcode_or_pc_is_a_site_mismatch(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10)],regs=regs)
        result=compare(tr,ref((BASE,'add',11,None)),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['opcode_or_pc_mismatch_indices'],[0])
        self.assertEqual(result['result_value_mismatch_indices'],[])

    def test_result_value_mismatch_distinct(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10)],regs=regs)
        result=compare(tr,ref((BASE,'addu',12,None)),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['result_value_mismatch_indices'],[0])
        self.assertFalse(result['matches_reference'])

    def test_multiply_hi_mismatch_distinct(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        tr,_=replay([r(25,8,9)],regs=regs)
        result=compare(tr,ref((BASE,'multu',0xfffffffe,2)),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['secondary_result_mismatch_indices'],[0])

    def test_both_multiply_halves_mismatch_in_one_event(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        tr,_=replay([r(25,8,9)],regs=regs)
        result=compare(tr,ref((BASE,'multu',0xfffffffd,2)),
                       guest_stopped_at_expected_pc=True)
        self.assertFalse(result['matches_reference'])
        self.assertEqual(result['result_value_mismatch_indices'],[0])
        self.assertEqual(result['secondary_result_mismatch_indices'],[0])
        self.assertEqual(result['mismatching_event_indices'],[0])
        self.assertEqual(result['matching_event_count'],0)
        self.assertFalse(result['mismatch_indices_truncated'])
        self.assertNotIn(hex(BASE),str(result))
        self.assertNotIn('fffffffd',str(result))

    def test_dual_mismatches_do_not_double_count_or_undercount_matching(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        count=40
        tr,_=replay([r(25,8,9)]*count,regs=regs)
        expected=ref(*((BASE+4*j,'multu',0xfffffffd,2)
                       for j in range(count)))
        result=compare(tr,expected,guest_stopped_at_expected_pc=True)
        self.assertEqual(result['matching_event_count'],0)
        self.assertEqual(result['mismatching_event_indices'],
                         list(range(MAX_MISMATCH_INDICES)))
        self.assertEqual(result['result_value_mismatch_indices'],
                         list(range(MAX_MISMATCH_INDICES)))
        self.assertEqual(result['secondary_result_mismatch_indices'],
                         list(range(MAX_MISMATCH_INDICES)))
        self.assertTrue(result['mismatch_indices_truncated'])

    def test_wrong_site_does_not_assign_numeric_mismatch_categories(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        tr,_=replay([r(25,8,9)],regs=regs)
        result=compare(tr,ref((BASE+4,'multu',0xfffffffd,2)),
                       guest_stopped_at_expected_pc=True)
        self.assertEqual(result['opcode_or_pc_mismatch_indices'],[0])
        self.assertEqual(result['result_value_mismatch_indices'],[])
        self.assertEqual(result['secondary_result_mismatch_indices'],[])
        self.assertEqual(result['matching_event_count'],0)

    def test_same_value_intermediate_is_not_deduplicated(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10),r(33,rs=8,rt=9,rd=10)],regs=regs)
        result=compare(tr,ref((BASE,'addu',11,None)),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['mismatching_event_indices'],[1])

    def test_incomplete_guest_withholds_mismatch_indices(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10),0],regs=regs,max_steps=1)
        result=compare(tr,ref(),guest_stopped_at_expected_pc=False)
        self.assertFalse(result['comparison_performed'])
        self.assertEqual(result['mismatching_event_indices'],[])
        self.assertIsNone(result['matching_event_count'])

    def test_mismatch_indices_are_bounded(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10)]*50,regs=regs)
        result=compare(tr,ref(),guest_stopped_at_expected_pc=True)
        self.assertEqual(len(result['mismatching_event_indices']),MAX_MISMATCH_INDICES)
        self.assertTrue(result['mismatch_indices_truncated'])

    def test_valid_hex_expected_is_allowed(self):
        x=decode({'schema':SCHEMA,'events':[{'pc':hex(BASE),'kind':'addu',
                'result_u32':'0xffffffff','secondary_u32':None}]})
        self.assertEqual(x,((BASE,'addu',0xffffffff,None),))

    def test_bad_fixture_fields_are_rejected(self):
        bad=[{}, {'schema':SCHEMA,'events':{}},
             {'schema':'bad','events':[]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'kind':'addu','result_u32':1}]},
             {'schema':SCHEMA,'events':[{'pc':BASE+1,'kind':'addu','result_u32':1,'secondary_u32':None}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'kind':'jal','result_u32':1,'secondary_u32':None}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'kind':'mflo','result_u32':1,'secondary_u32':0}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'kind':'mult','result_u32':1,'secondary_u32':None}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'kind':'addu','result_u32':True,'secondary_u32':None}]}]
        for item in bad:
            with self.subTest(case=item),self.assertRaises(ValueError):decode(item)

    def test_corrupted_trace_pc_order_fails(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10)],regs=regs)
        tr['arithmetic_accesses']=((BASE+4,'addu',11,None),)
        with self.assertRaises(ValueError):trace_events(tr)

    def test_corrupted_trace_values_are_rejected(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        tr,_=replay([r(33,rs=8,rt=9,rd=10)],regs=regs)
        tr['arithmetic_accesses']=((BASE,'addu',-1,None),)
        with self.assertRaises(ValueError):trace_events(tr)

    def test_safe_report_does_not_expose_pc_or_arithmetic_numbers(self):
        regs=[0]*32;regs[8]=0xfffff000;regs[9]=4096
        tr,_=replay([r(24,8,9)],regs=regs)
        result=compare(tr,ref((BASE,'mult',0,0)),guest_stopped_at_expected_pc=True)
        self.assertNotIn(hex(BASE),str(result))
        self.assertNotIn('ff000000',str(result))
        self.assertFalse(result['private_values_emitted'])

if __name__=='__main__':unittest.main()
