"""Executed store order includes temporary and equal-value writes."""
import unittest
from tools.mips_store_event_sequence import (
    SCHEMA, MAX_MISMATCH_INDICES, decode, compare, trace_events)
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
import struct

BASE=0x80010000
RAM=0x80110000


def op(code,rs=0,rt=0,imm=0):
    return (code<<26)|(rs<<21)|(rt<<16)|(imm&65535)


def replay(words, *, writable=True, max_steps=100):
    image=struct.pack('<%dI'%len(words),*words)
    mem=MappedMemory().map_region(BASE,image).map_region(RAM,bytes(64),writable=writable)
    regs=[0]*32
    regs[5]=RAM;regs[8]=123
    trace=execute(image,BASE,BASE,mem,regs,max_steps=max_steps)
    return trace,mem


def expected(*events):
    return decode({'schema':SCHEMA,'events':[
        {'pc':pc,'address':addr,'width':width} for pc,addr,width in events]})


class StoreEventSequenceTests(unittest.TestCase):
    def test_all_three_store_widths_are_recorded_in_execution_order(self):
        words=[op(40,5,8,0),op(41,5,8,2),op(43,5,8,4)]
        trace,_=replay(words)
        self.assertEqual(trace['store_accesses'],(
            (BASE,RAM,1,8),(BASE+4,RAM+2,2,8),(BASE+8,RAM+4,4,8)))
        e=expected((BASE,RAM,1),(BASE+4,RAM+2,2),(BASE+8,RAM+4,4))
        r=compare(trace,e,guest_stopped_at_expected_pc=True)
        self.assertTrue(r['matches_reference'])
        self.assertEqual(r['executed_store_width_counts'],{'1':1,'2':1,'4':1})

    def test_same_value_writes_still_count_as_two_events(self):
        trace,_=replay([op(40,5,8,0),op(40,5,8,0)])
        self.assertEqual(len(trace['store_accesses']),2)
        r=compare(trace,expected((BASE,RAM,1)),guest_stopped_at_expected_pc=True)
        self.assertEqual(r['mismatching_event_indices'],[1])
        self.assertFalse(r['matches_reference'])

    def test_transient_write_then_restore_is_not_ignored(self):
        trace,mem=replay([op(40,5,8,0),op(40,5,0,0)])
        self.assertEqual(mem.read(RAM,1),0)
        self.assertEqual(len(trace['store_accesses']),2)
        r=compare(trace,expected(),guest_stopped_at_expected_pc=True)
        self.assertEqual(r['mismatching_event_indices'],[0,1])

    def test_order_is_significant_with_same_final_ram(self):
        a,_=replay([op(40,5,8,0),op(40,5,0,0)])
        b,_=replay([op(40,5,0,0),op(40,5,8,0),op(40,5,0,0)])
        e=expected(*[(p,addr,w) for p,addr,w,_ in a['store_accesses']])
        r=compare(b,e,guest_stopped_at_expected_pc=True)
        self.assertFalse(r['matches_reference'])

    def test_different_effective_address_is_detected(self):
        trace,_=replay([op(41,5,8,2)])
        e=expected((BASE,RAM+4,2))
        self.assertEqual(compare(trace,e,guest_stopped_at_expected_pc=True)
                         ['mismatching_event_indices'],[0])

    def test_width_mismatch_is_detected(self):
        trace,_=replay([op(40,5,8,1)])
        e=expected((BASE,RAM,2))
        self.assertEqual(compare(trace,e,guest_stopped_at_expected_pc=True)
                         ['mismatching_event_indices'],[0])

    def test_pc_mismatch_is_detected(self):
        trace,_=replay([0,op(40,5,8,1)])
        e=expected((BASE,RAM+1,1))
        self.assertEqual(compare(trace,e,guest_stopped_at_expected_pc=True)
                         ['mismatching_event_indices'],[0])

    def test_unmapped_or_readonly_store_creates_no_success_event(self):
        tr,_=replay([op(41,5,8,0)],writable=False)
        self.assertFalse(tr['completed'])
        self.assertEqual(tr['store_addresses'],())
        self.assertEqual(tr['store_accesses'],())

    def test_incomplete_run_withholds_mismatching_event_positions(self):
        trace,_=replay([op(40,5,8,0),op(40,5,8,1)],max_steps=1)
        r=compare(trace,expected(),guest_stopped_at_expected_pc=False)
        self.assertFalse(r['comparison_performed'])
        self.assertEqual(r['mismatching_event_indices'],[])
        self.assertEqual(r['executed_store_count'],1)

    def test_extra_expected_event_is_reported_as_missing(self):
        trace,_=replay([op(40,5,8,0)])
        e=expected((BASE,RAM,1),(BASE+4,RAM+1,1))
        r=compare(trace,e,guest_stopped_at_expected_pc=True)
        self.assertEqual(r['mismatching_event_indices'],[1])

    def test_mismatch_indices_capped_for_privacy_and_output_size(self):
        words=[op(40,5,8,i) for i in range(50)]
        trace,_=replay(words)
        r=compare(trace,expected(),guest_stopped_at_expected_pc=True)
        self.assertEqual(len(r['mismatching_event_indices']),MAX_MISMATCH_INDICES)
        self.assertTrue(r['mismatch_indices_truncated'])

    def test_decoder_accepts_hex_words_in_private_reference(self):
        raw={'schema':SCHEMA,'events':[{'pc':hex(BASE),'address':hex(RAM),'width':1}]}
        self.assertEqual(decode(raw),((BASE,RAM,1),))

    def test_decoder_rejects_malformed_or_extra_private_metadata(self):
        bad=[{}, {'schema':SCHEMA,'events':None},
             {'schema':'unknown','events':[]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,'width':1,'value':123}]},
             {'schema':SCHEMA,'events':[{'pc':BASE+1,'address':RAM,'width':1}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM+1,'width':2}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,'width':8}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,'width':True}]}]
        for obj in bad:
            with self.subTest(obj=obj),self.assertRaises(ValueError):decode(obj)

    def test_report_does_not_expose_pc_memory_address_or_values(self):
        trace,_=replay([op(40,5,8,0)])
        report=compare(trace,expected((BASE,RAM,1)),guest_stopped_at_expected_pc=True)
        self.assertNotIn(hex(BASE),str(report))
        self.assertNotIn(hex(RAM),str(report))
        self.assertNotIn('123',str(report))
        self.assertFalse(report['store_sequence_capture_authenticated'])
        self.assertFalse(report['private_values_emitted'])

    def test_corrupt_trace_address_disagreement_fails_closed(self):
        trace,_=replay([op(40,5,8,0)])
        trace['store_addresses']=(RAM+1,)
        with self.assertRaises(ValueError):trace_events(trace)

    def test_corrupt_trace_missing_store_accesses_fails_closed(self):
        trace,_=replay([op(40,5,8,0)])
        trace.pop('store_accesses')
        with self.assertRaises(ValueError):trace_events(trace)


if __name__=='__main__': unittest.main()
