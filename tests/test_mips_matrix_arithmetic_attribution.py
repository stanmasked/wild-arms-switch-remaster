"""Conservative numeric-mismatch to final matrix SH dataflow fixtures."""
import struct
import unittest

from tools.mips_matrix_arithmetic_attribution import analyze, MAX_REPORTED_INDICES
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_arithmetic_event_sequence import decode, SCHEMA
from tests.test_ps1_arithmetic_capture import synthetic_builder, reg
from tests.test_mips_ps1_matrix_reference import BASE, MATRIX, op, fixture
from tools.mips_ps1_matrix_reference import compare


def report(reference, mutate=None):
    blob, capture, arithmetic = synthetic_builder()
    if mutate is not None:
        mutate(arithmetic)
    capture['expected_arithmetic_events'] = arithmetic
    return compare(blob, capture)['arithmetic_matrix_attribution']


def custom(words, regs=None, *, snapshots=None, matrix=MATRIX):
    image=struct.pack('<%dI'%len(words), *words)
    memory=MappedMemory().map_region(BASE,image)
    memory.map_region(matrix,bytes(18),writable=True)
    for base,data in (snapshots or []):
        memory.map_region(base,data,writable=True)
    state=[0]*32 if regs is None else list(regs)
    state[5]=matrix
    trace=execute(image,BASE,BASE,memory,state)
    private_reference=decode({'schema':SCHEMA,'events':[
        {'pc':pc,'kind':kind,'result_u32':result,'secondary_u32':secondary}
        for pc,kind,result,secondary in trace['arithmetic_accesses']]})
    return image, trace, private_reference


class AttributionTests(unittest.TestCase):
    def test_no_numeric_mismatch_has_no_affected_slots(self):
        result=report(None)
        self.assertTrue(result['attribution_performed'])
        self.assertEqual(result['candidate_affected_slot_indices'],[])
        self.assertTrue(all(s['final_sh_observed'] for s in result['matrix_slots']))
        self.assertFalse(result['proven_numeric_causation'])

    def test_bad_mult_lo_only_reaches_its_own_coefficient(self):
        result=report(None,lambda v:v['events'][8].update(result_u32=8))
        self.assertEqual(result['candidate_affected_slot_indices'],[2])
        self.assertEqual(result['matrix_slots'][2]['candidate_primary_mismatch_indices'],[8])
        self.assertEqual(result['matrix_slots'][0]['candidate_mismatch_event_indices'],[])

    def test_bad_mflo_and_sra_indices_both_reach_same_slot(self):
        def mutate(v):
            v['events'][1]['result_u32']=4
            v['events'][2]['result_u32']=5
        result=report(None,mutate)
        self.assertEqual(result['candidate_affected_slot_indices'],[0])
        self.assertEqual(result['matrix_slots'][0]['candidate_mismatch_event_indices'],[1,2])

    def test_multiplication_hi_mismatch_does_not_reach_mflo_path(self):
        result=report(None,lambda v:v['events'][0].update(secondary_u32=8))
        self.assertEqual(result['candidate_affected_slot_indices'],[])
        self.assertEqual(result['mismatching_events_without_final_matrix_dependency'],[0])

    def test_hi_mismatch_can_reach_mfhi_derived_matrix(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        words=[reg(25,8,9),reg(16,rd=11)]+[op(41,5,11,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        mismatch=list(expected)
        pc,kind,value,hi=mismatch[0]
        mismatch[0]=(pc,kind,value,hi+1)
        result=analyze(image,BASE,trace,MATRIX,tuple(mismatch),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],list(range(9)))
        self.assertEqual(result['matrix_slots'][0]['candidate_hi_mismatch_indices'],[0])
        self.assertEqual(result['matrix_slots'][0]['candidate_primary_mismatch_indices'],[])

    def test_simultaneous_lo_hi_mismatch_reaches_distinct_final_sh_slots(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        words=[reg(25,8,9),reg(18,rd=11),reg(16,rd=12),
               op(41,5,11,0),op(41,5,12,2)]
        words += [op(41,5,0,2*i) for i in range(2,9)]
        image,trace,expected=custom(words,regs)
        changed=list(expected)
        pc,kind,lo,hi=changed[0]
        changed[0]=(pc,kind,(lo+1)&0xffffffff,(hi+1)&0xffffffff)
        result=analyze(image,BASE,trace,MATRIX,tuple(changed),
                       guest_stopped_at_expected_pc=True)
        self.assertTrue(result['attribution_performed'])
        self.assertEqual(result['candidate_affected_slot_indices'],[0,1])
        self.assertEqual(result['matrix_slots'][0]['candidate_primary_mismatch_indices'],[0])
        self.assertEqual(result['matrix_slots'][0]['candidate_hi_mismatch_indices'],[])
        self.assertEqual(result['matrix_slots'][1]['candidate_primary_mismatch_indices'],[])
        self.assertEqual(result['matrix_slots'][1]['candidate_hi_mismatch_indices'],[0])
        self.assertEqual(result['mismatching_events_without_final_matrix_dependency'],[])
        self.assertFalse(result['proven_numeric_causation'])

    def test_lo_mismatch_cannot_reach_mfhi_only_path(self):
        regs=[0]*32;regs[8]=0xffffffff;regs[9]=2
        words=[reg(25,8,9),reg(16,rd=11)]+[op(41,5,11,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        mismatch=list(expected)
        pc,kind,value,hi=mismatch[0]
        mismatch[0]=(pc,kind,value-1,hi)
        result=analyze(image,BASE,trace,MATRIX,tuple(mismatch),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],[])
        self.assertEqual(result['mismatching_events_without_final_matrix_dependency'],[0])

    def test_aligned_reference_wrong_pc_refuses_attribution(self):
        def mutate(v): v['events'][0]['pc']=BASE+4
        result=report(None,mutate)
        self.assertFalse(result['attribution_performed'])
        self.assertEqual(result['reason_code'],'arithmetic_event_alignment_failed')
        self.assertEqual(result['candidate_affected_slot_indices'],[])

    def test_wrong_kind_refuses_attribution(self):
        result=report(None,lambda v:v['events'][0].update(kind='multu'))
        self.assertFalse(result['attribution_performed'])
        self.assertFalse(result['reference_event_alignment_confirmed'])

    def test_missing_reference_event_refuses_alignment(self):
        result=report(None,lambda v:v['events'].pop())
        self.assertFalse(result['attribution_performed'])
        self.assertEqual(result['reason_code'],'arithmetic_event_alignment_failed')

    def test_guest_step_limit_withholds_dependencies(self):
        blob,capture,arith=synthetic_builder()
        capture['expected_arithmetic_events']=arith
        capture['max_steps']=3
        result=compare(blob,capture)['arithmetic_matrix_attribution']
        self.assertFalse(result['attribution_performed'])
        self.assertEqual(result['reason_code'],'incomplete_guest_execution')
        self.assertFalse(any(s['final_sh_observed'] for s in result['matrix_slots']))

    def test_overwritten_register_drops_old_mismatch_dependency(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=11),reg(33,rs=0,rt=0,rd=11)]
        words += [op(41,5,11,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        mismatch=list(expected)
        mismatch[0]=(mismatch[0][0],'addu',12,None)
        result=analyze(image,BASE,trace,MATRIX,tuple(mismatch),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],[])
        self.assertEqual(result['mismatching_events_without_final_matrix_dependency'],[0])

    def test_overwritten_halfword_drops_previous_mismatch_dependency(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=11),op(41,5,11,0),
               op(41,5,0,0)]+[op(41,5,0,2*i) for i in range(1,9)]
        image,trace,expected=custom(words,regs)
        expected=((BASE,'addu',12,None),)
        result=analyze(image,BASE,trace,MATRIX,expected,guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],[])
        self.assertTrue(result['matrix_slots'][0]['final_sh_observed'])

    def test_partial_sw_overlap_revokes_final_sh_provenance(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=11)]+[op(41,5,11,2*i) for i in range(9)]+[op(43,5,0,0)]
        image,trace,events=custom(words,regs)
        mismatch=((BASE,'addu',12,None),)
        result=analyze(image,BASE,trace,MATRIX,mismatch,guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],list(range(2,9)))
        self.assertFalse(result['matrix_slots'][0]['final_sh_observed'])
        self.assertFalse(result['matrix_slots'][1]['final_sh_observed'])

    def test_spill_to_ram_and_reload_propagates_mismatch_after_load_delay(self):
        regs=[0]*32;regs[8]=1024;regs[9]=2048
        words=[reg(24,8,9),reg(18,rd=10),reg(3,rt=10,rd=11,sa=12),
               op(43,5,11,40),op(35,5,12,40),0,
               op(41,5,12,0)]+[op(41,5,0,2*i) for i in range(1,9)]
        image,trace,expected=custom(words,regs,snapshots=[(MATRIX+40,bytes(4))])
        mismatch=list(expected)
        pc,kind,value,secondary=mismatch[2]
        mismatch[2]=(pc,kind,value+1,secondary)
        result=analyze(image,BASE,trace,MATRIX,tuple(mismatch),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],[0])
        self.assertEqual(result['matrix_slots'][0]['candidate_mismatch_event_indices'],[2])

    def test_load_delay_first_store_does_not_inherit_newly_loaded_tokens(self):
        regs=[0]*32;regs[8]=4;regs[9]=7;regs[11]=0
        words=[reg(33,rs=8,rt=9,rd=10),op(43,5,10,40),
               op(35,5,11,40),op(41,5,11,0),op(41,5,11,2)]
        words += [op(41,5,0,2*i) for i in range(2,9)]
        image,trace,expected=custom(words,regs,snapshots=[(MATRIX+40,bytes(4))])
        mismatch=((BASE,'addu',12,None),)
        result=analyze(image,BASE,trace,MATRIX,mismatch,guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],[1])
        self.assertEqual(result['matrix_slots'][0]['candidate_mismatch_event_indices'],[])

    def test_zero_register_arithmetic_result_not_attributed(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=0)]+[op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        result=analyze(image,BASE,trace,MATRIX,((BASE,'addu',1,None),),guest_stopped_at_expected_pc=True)
        self.assertEqual(result['candidate_affected_slot_indices'],[])

    def test_mismatch_derived_matrix_store_pointer_withholds_all_slots(self):
        regs=[0]*32;regs[8]=MATRIX;regs[9]=0
        words=[reg(33,rs=8,rt=9,rd=5)]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        wrong=list(expected)
        pc,kind,value,aux=wrong[0]
        wrong[0]=(pc,kind,(value+2)&0xffffffff,aux)
        result=analyze(image,BASE,trace,MATRIX,tuple(wrong),
                       guest_stopped_at_expected_pc=True)
        self.assertTrue(result['reference_event_alignment_confirmed'])
        self.assertFalse(result['attribution_performed'])
        self.assertEqual(result['reason_code'],'mismatch_dependent_execution_path')
        self.assertTrue(result['mismatch_dependent_address_observed'])
        self.assertFalse(result['mismatch_dependent_control_observed'])
        self.assertEqual(result['candidate_affected_slot_indices'],[])
        self.assertEqual(result['mismatching_events_without_final_matrix_dependency'],[])
        self.assertFalse(any(slot['final_sh_observed'] for slot in result['matrix_slots']))
        self.assertNotIn(hex(MATRIX),str(result))

    def test_mismatch_derived_load_pointer_withholds_attribution(self):
        regs=[0]*32;regs[8]=MATRIX+40;regs[9]=0
        words=[reg(33,rs=8,rt=9,rd=6),
               op(35,6,11,0),0,op(41,5,11,0)]
        words += [op(41,5,0,2*i) for i in range(1,9)]
        image,trace,expected=custom(words,regs,
                                    snapshots=[(MATRIX+40,bytes(4))])
        wrong=list(expected)
        pc,kind,value,aux=wrong[0]
        wrong[0]=(pc,kind,(value+4)&0xffffffff,aux)
        result=analyze(image,BASE,trace,MATRIX,tuple(wrong),
                       guest_stopped_at_expected_pc=True)
        self.assertFalse(result['attribution_performed'])
        self.assertTrue(result['mismatch_dependent_address_observed'])
        self.assertFalse(result['mismatch_dependent_control_observed'])

    def test_mismatch_derived_beq_condition_withholds_attribution(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),op(4,10,0,1),0]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        wrong=list(expected)
        pc,kind,value,aux=wrong[0]
        wrong[0]=(pc,kind,12,aux)
        result=analyze(image,BASE,trace,MATRIX,tuple(wrong),
                       guest_stopped_at_expected_pc=True)
        self.assertFalse(result['attribution_performed'])
        self.assertFalse(result['mismatch_dependent_address_observed'])
        self.assertTrue(result['mismatch_dependent_control_observed'])
        self.assertEqual(result['reason_code'],'mismatch_dependent_execution_path')

    def test_mismatch_derived_jr_target_withholds_attribution(self):
        regs=[0]*32;regs[8]=BASE+12;regs[9]=0
        words=[reg(33,rs=8,rt=9,rd=10),reg(8,rs=10),0]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        wrong=list(expected)
        pc,kind,value,aux=wrong[0]
        wrong[0]=(pc,kind,(value+4)&0xffffffff,aux)
        result=analyze(image,BASE,trace,MATRIX,tuple(wrong),
                       guest_stopped_at_expected_pc=True)
        self.assertFalse(result['attribution_performed'])
        self.assertTrue(result['mismatch_dependent_control_observed'])
        self.assertFalse(result['mismatch_dependent_address_observed'])

    def test_matching_arithmetic_in_memory_pointer_is_not_ambiguous(self):
        regs=[0]*32;regs[8]=MATRIX;regs[9]=0
        words=[reg(33,rs=8,rt=9,rd=5)]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        result=analyze(image,BASE,trace,MATRIX,expected,
                       guest_stopped_at_expected_pc=True)
        self.assertTrue(result['attribution_performed'])
        self.assertFalse(result['mismatch_dependent_address_observed'])
        self.assertFalse(result['mismatch_dependent_control_observed'])
        self.assertTrue(all(slot['final_sh_observed'] for slot in result['matrix_slots']))

    def test_overwritten_mismatch_does_not_taint_later_branch(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),
               reg(33,rs=0,rt=0,rd=10),op(4,10,0,1),0]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        wrong=list(expected)
        pc,kind,value,aux=wrong[0]
        wrong[0]=(pc,kind,12,aux)
        result=analyze(image,BASE,trace,MATRIX,tuple(wrong),
                       guest_stopped_at_expected_pc=True)
        self.assertTrue(result['attribution_performed'])
        self.assertFalse(result['mismatch_dependent_control_observed'])
        self.assertEqual(result['mismatching_events_without_final_matrix_dependency'],[0])

    def test_spill_reload_then_branch_uses_delayed_mismatch(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),
               op(43,5,10,40),op(35,5,11,40),0,op(4,11,0,1),0]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs,snapshots=[(MATRIX+40,bytes(4))])
        changed=list(expected)
        pc,kind,value,aux=changed[0]
        changed[0]=(pc,kind,12,aux)
        outcome=analyze(image,BASE,trace,MATRIX,tuple(changed),
                        guest_stopped_at_expected_pc=True)
        self.assertFalse(outcome['attribution_performed'])
        self.assertTrue(outcome['mismatch_dependent_control_observed'])
        self.assertFalse(outcome['mismatch_dependent_address_observed'])
        self.assertEqual(outcome['reason_code'],'mismatch_dependent_execution_path')

    def test_overwritten_spill_breaks_dependency_before_branch(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),op(43,5,10,40),
               op(43,5,0,40),op(35,5,11,40),0,op(4,11,0,1),0]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs,snapshots=[(MATRIX+40,bytes(4))])
        changed=list(expected)
        pc,kind,value,aux=changed[0]
        changed[0]=(pc,kind,12,aux)
        outcome=analyze(image,BASE,trace,MATRIX,tuple(changed),
                        guest_stopped_at_expected_pc=True)
        self.assertTrue(outcome['attribution_performed'])
        self.assertFalse(outcome['mismatch_dependent_control_observed'])
        self.assertEqual(outcome['candidate_affected_slot_indices'],[])
        self.assertEqual(outcome['mismatching_events_without_final_matrix_dependency'],[0])

    def test_back_to_back_loads_keep_old_token_until_second_load_retires(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),op(43,5,10,40),
               op(43,5,0,44),op(35,5,11,40),op(35,5,11,44),
               op(41,5,11,0),op(41,5,11,2)]
        words += [op(41,5,0,2*i) for i in range(2,9)]
        image,trace,expected=custom(words,regs,snapshots=[(MATRIX+40,bytes(8))])
        changed=list(expected)
        pc,kind,value,aux=changed[0]
        changed[0]=(pc,kind,12,aux)
        outcome=analyze(image,BASE,trace,MATRIX,tuple(changed),
                        guest_stopped_at_expected_pc=True)
        self.assertTrue(outcome['attribution_performed'])
        self.assertEqual(outcome['candidate_affected_slot_indices'],[0])
        self.assertEqual(outcome['matrix_slots'][0]['candidate_mismatch_event_indices'],[0])
        self.assertEqual(outcome['matrix_slots'][1]['candidate_mismatch_event_indices'],[])

    def test_immediate_alu_write_supersedes_old_pending_load_lineage(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),op(43,5,10,40),
               op(35,5,11,40),reg(33,rs=0,rt=0,rd=11)]
        words += [op(41,5,11,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs,snapshots=[(MATRIX+40,bytes(4))])
        changed=list(expected)
        pc,kind,value,aux=changed[0]
        changed[0]=(pc,kind,12,aux)
        outcome=analyze(image,BASE,trace,MATRIX,tuple(changed),
                        guest_stopped_at_expected_pc=True)
        self.assertTrue(outcome['attribution_performed'])
        self.assertEqual(outcome['candidate_affected_slot_indices'],[])
        self.assertEqual(outcome['mismatching_events_without_final_matrix_dependency'],[0])

    def test_arithmetic_inside_branch_delay_slot_cannot_change_taken_target(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[op(4,0,0,1),reg(33,rs=8,rt=9,rd=10)]
        words += [op(41,5,10,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        changed=list(expected)
        pc,kind,value,aux=changed[0]
        changed[0]=(pc,kind,12,aux)
        outcome=analyze(image,BASE,trace,MATRIX,tuple(changed),
                        guest_stopped_at_expected_pc=True)
        self.assertTrue(outcome['attribution_performed'])
        self.assertFalse(outcome['mismatch_dependent_control_observed'])
        self.assertEqual(outcome['candidate_affected_slot_indices'],list(range(9)))

    def test_branch_likely_annulled_slot_does_not_emit_arithmetic_event(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),op(20,10,0,1),
               reg(33,rs=8,rt=9,rd=11)]
        words += [op(41,5,0,2*i) for i in range(9)]
        image,trace,expected=custom(words,regs)
        self.assertNotIn(BASE+8,trace['visited_pcs'])
        self.assertEqual(len(expected),1)
        changed=list(expected)
        pc,kind,value,aux=changed[0]
        changed[0]=(pc,kind,12,aux)
        outcome=analyze(image,BASE,trace,MATRIX,tuple(changed),
                        guest_stopped_at_expected_pc=True)
        self.assertFalse(outcome['attribution_performed'])
        self.assertTrue(outcome['mismatch_dependent_control_observed'])
        self.assertEqual(outcome['reason_code'],'mismatch_dependent_execution_path')

    def test_guest_write_to_executable_image_withholds_all_attribution(self):
        regs=[0]*32;regs[5]=MATRIX;regs[6]=BASE
        regs[8]=4;regs[9]=7
        words=[reg(33,rs=8,rt=9,rd=10),op(43,6,0,0)]
        words += [op(41,5,10,2*i) for i in range(9)]
        image=struct.pack('<%dI'%len(words),*words)
        memory=MappedMemory().map_region(BASE,image,writable=True)
        memory.map_region(MATRIX,bytes(18),writable=True)
        trace=execute(image,BASE,BASE,memory,regs)
        self.assertTrue(trace['completed'])
        mismatch=((BASE,'addu',12,None),)
        outcome=analyze(image,BASE,trace,MATRIX,mismatch,
                        guest_stopped_at_expected_pc=True)
        self.assertFalse(outcome['attribution_performed'])
        self.assertEqual(outcome['reason_code'],'guest_code_write_unmodeled')
        self.assertTrue(outcome['executed_code_write_observed'])
        self.assertEqual(outcome['candidate_affected_slot_indices'],[])
        self.assertEqual(outcome['mismatching_events_without_final_matrix_dependency'],[])
        self.assertFalse(outcome['proven_numeric_causation'])
        self.assertNotIn(hex(BASE),str(outcome))

    def test_same_value_guest_code_store_still_withholds_attribution(self):
        regs=[0]*32;regs[6]=BASE;regs[8]=4;regs[9]=7
        first=reg(33,rs=8,rt=9,rd=10)
        regs[11]=first
        words=[first,op(43,6,11,0)]
        words += [op(41,5,10,2*i) for i in range(9)]
        image=struct.pack('<%dI'%len(words),*words)
        memory=MappedMemory().map_region(BASE,image,writable=True)
        memory.map_region(MATRIX,bytes(18),writable=True)
        regs[5]=MATRIX
        trace=execute(image,BASE,BASE,memory,regs)
        self.assertTrue(trace['completed'])
        outcome=analyze(image,BASE,trace,MATRIX,((BASE,'addu',12,None),),
                        guest_stopped_at_expected_pc=True)
        self.assertEqual(outcome['reason_code'],'guest_code_write_unmodeled')
        self.assertTrue(outcome['executed_code_write_observed'])

    def test_wrong_store_trace_fails_closed(self):
        regs=[0]*32;regs[8]=4;regs[9]=7
        image,trace,expected=custom([reg(33,rs=8,rt=9,rd=10),op(41,5,10,0)],regs)
        trace['store_addresses']=(MATRIX+2,)
        with self.assertRaises(ValueError):
            analyze(image,BASE,trace,MATRIX,expected,guest_stopped_at_expected_pc=True)

    def test_report_does_not_contain_values_pc_or_guest_addresses(self):
        result=report(None,lambda v:v['events'][0].update(result_u32=7))
        self.assertNotIn(hex(BASE),str(result))
        self.assertNotIn(hex(MATRIX),str(result))
        self.assertNotIn('result_u32',str(result))
        self.assertFalse(result['private_values_emitted'])

    def test_maximum_reported_indices_is_fixed(self):
        self.assertEqual(MAX_REPORTED_INDICES,32)

if __name__=='__main__':unittest.main()
