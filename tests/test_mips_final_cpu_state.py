"""Synthetic post-return R3000A CPU state comparison and privacy tests."""
import unittest
from tools.mips_final_cpu_state import decode_expected, compare


def state(*, pending=None):
    return {'gpr':[0]+[i for i in range(1,32)], 'hi':'0x00001000',
            'lo':0x80000000,'pending_load':pending,'in_branch_delay_slot':False}


def executed(ref=None):
    ref=decode_expected(state()) if ref is None else ref
    return {'gpr':ref['gpr'], 'hi':ref['hi'],'lo':ref['lo'],
            'pending_load':ref['pending_load'], 'completed':True,'reason':'stop_pc'}


class FinalCPUStateTests(unittest.TestCase):
    def test_matches_all_32_gprs_hi_lo_and_empty_pipeline(self):
        ref=decode_expected(state())
        result=compare(executed(ref),ref,guest_stopped_at_expected_pc=True)
        self.assertTrue(result['final_cpu_state_matches_reference'])
        self.assertEqual(result['matching_gpr_count'],32)
        self.assertEqual(result['mismatching_gpr_indices'],[])
        self.assertTrue(result['hi_matches_reference'])
        self.assertTrue(result['lo_matches_reference'])
        self.assertTrue(result['pending_load_matches_reference'])
        self.assertFalse(result['actual_ps1_hardware_state_authenticated'])

    def test_mismatching_gprs_only_publish_indices(self):
        ref=decode_expected(state())
        trace=executed(ref)
        regs=list(trace['gpr']);regs[8]=4096;regs[31]=0x87654321
        report=compare({**trace,'gpr':regs},ref,guest_stopped_at_expected_pc=True)
        self.assertEqual(report['mismatching_gpr_indices'],[8,31])
        self.assertEqual(report['matching_gpr_count'],30)
        self.assertFalse(report['final_cpu_state_matches_reference'])
        self.assertNotIn('4096',str(report))
        self.assertNotIn('87654321',str(report))

    def test_hi_only_mismatch(self):
        ref=decode_expected(state())
        actual={**executed(ref),'hi':4}
        r=compare(actual,ref,guest_stopped_at_expected_pc=True)
        self.assertEqual(r['mismatching_gpr_indices'],[])
        self.assertFalse(r['hi_matches_reference'])
        self.assertTrue(r['lo_matches_reference'])
        self.assertFalse(r['final_cpu_state_matches_reference'])

    def test_lo_only_mismatch(self):
        ref=decode_expected(state())
        r=compare({**executed(ref),'lo':0},ref,guest_stopped_at_expected_pc=True)
        self.assertTrue(r['hi_matches_reference'])
        self.assertFalse(r['lo_matches_reference'])

    def test_pending_value_mismatch_is_boolean_only(self):
        ref=decode_expected(state(pending={'gpr':9,'value_u32':4096}))
        tr=executed(ref)
        r=compare({**tr,'pending_load':(9,7)},ref,guest_stopped_at_expected_pc=True)
        self.assertFalse(r['pending_load_matches_reference'])
        self.assertNotIn('4096',str(r))
        self.assertNotIn('pending_value',str(r))

    def test_pending_destination_mismatch(self):
        ref=decode_expected(state(pending={'gpr':9,'value_u32':'0x00001000'}))
        tr=executed(ref)
        r=compare({**tr,'pending_load':(8,4096)},ref,guest_stopped_at_expected_pc=True)
        self.assertFalse(r['final_cpu_state_matches_reference'])

    def test_pending_can_match(self):
        ref=decode_expected(state(pending={'gpr':9,'value_u32':4096}))
        r=compare(executed(ref),ref,guest_stopped_at_expected_pc=True)
        self.assertTrue(r['final_cpu_state_matches_reference'])

    def test_stop_not_reached_does_not_output_speculative_mismatches(self):
        ref=decode_expected(state())
        r=compare({**executed(ref),'hi':3},ref,guest_stopped_at_expected_pc=False)
        self.assertFalse(r['final_cpu_state_comparison_performed'])
        self.assertFalse(r['final_cpu_state_matches_reference'])
        self.assertIsNone(r['matching_gpr_count'])
        self.assertIsNone(r['hi_matches_reference'])
        self.assertEqual(r['mismatching_gpr_indices'],[])

    def test_missing_fields_and_extra_fields_rejected(self):
        for bad in ({}, {'gpr':[]}, {**state(),'secret':1},
                    {k:v for k,v in state().items() if k!='lo'}):
            with self.subTest(bad=sorted(bad)), self.assertRaises(ValueError):
                decode_expected(bad)

    def test_invalid_register_count_and_zero_rejected(self):
        bad=state();bad['gpr']=bad['gpr'][:31]
        with self.assertRaises(ValueError):decode_expected(bad)
        bad=state();bad['gpr'][0]=1
        with self.assertRaises(ValueError):decode_expected(bad)

    def test_bad_word_ranges_and_nonintegers_fail_closed(self):
        for bad_value in (-1,1<<32,True,False,'1234','0x100000000',None):
            for field in ('hi','lo'):
                s=state();s[field]=bad_value
                with self.subTest(value=bad_value,field=field),self.assertRaises(ValueError):
                    decode_expected(s)

    def test_bad_post_branch_slot_is_unsupported(self):
        for value in (True,'false',0,1,None):
            s=state();s['in_branch_delay_slot']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                decode_expected(s)

    def test_bad_post_pending_load_rejected(self):
        for value in ({'gpr':0,'value_u32':1},{'gpr':32,'value_u32':1},
                      {'gpr':8,'value_u32':True},{'gpr':8,'value_u32':-1},
                      {'gpr':8,'value_u32':0x100000000},{'gpr':8},
                      {'gpr':8,'value_u32':2,'unknown':1},[8,7]):
            s=state();s['pending_load']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                decode_expected(s)

    def test_invalid_interpreter_result_rejected(self):
        ref=decode_expected(state())
        for bad in ({}, {'gpr':[0]}, {**executed(ref),'gpr':[0]*31},
                    {**executed(ref),'pending_load':(8,)},
                    {**executed(ref),'lo':None}):
            with self.subTest(keys=list(bad)),self.assertRaises(ValueError):
                compare(bad,ref,guest_stopped_at_expected_pc=True)

    def test_stop_flag_must_be_bool(self):
        ref=decode_expected(state())
        with self.assertRaises(ValueError):
            compare(executed(ref),ref,guest_stopped_at_expected_pc=1)

if __name__=='__main__':unittest.main()
