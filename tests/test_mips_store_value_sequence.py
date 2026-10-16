"""Independent concrete MIPS store-value checks, including transient stores."""
import struct
import unittest

from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_store_value_sequence import (
    SCHEMA, MAX_MISMATCH_INDICES, decode, compare, project_sites, trace_values,
)

BASE = 0x80010000
RAM = 0x80110000


def op(code,rs=0,rt=0,imm=0):
    return code<<26 | rs<<21 | rt<<16 | (imm & 65535)


def replay(words, *, regs=None, max_steps=100):
    image=struct.pack('<%dI'%len(words), *words)
    mem=(MappedMemory().map_region(BASE,image)
         .map_region(RAM,bytes(128),writable=True))
    state=[0]*32 if regs is None else regs
    state[5]=RAM
    trace=execute(image,BASE,BASE,mem,state,max_steps=max_steps)
    return trace,mem


def fixture(*records):
    return decode({'schema':SCHEMA, 'events':[
        {'pc':pc,'address':addr,'width':width,'value_u32':value}
        for pc,addr,width,value in records]})


class ValueSequenceTests(unittest.TestCase):
    def test_store_byte_truncates_full_gpr_to_eight_bits(self):
        regs=[0]*32;regs[8]=0x1234abfe
        trace,mem=replay([op(40,5,8,0)],regs=regs)
        self.assertEqual(trace['store_value_accesses'],((BASE,RAM,1,8,0xfe),))
        self.assertEqual(mem.read(RAM,1),0xfe)
        self.assertTrue(compare(trace,fixture((BASE,RAM,1,0xfe)),guest_stopped_at_expected_pc=True)['matches_reference'])

    def test_store_halfword_truncates_to_sixteen_bits(self):
        regs=[0]*32;regs[8]=0xdeadbeef
        trace,mem=replay([op(41,5,8,2)],regs=regs)
        self.assertEqual(trace['store_value_accesses'][0][-1],0xbeef)
        self.assertEqual(mem.read(RAM+2,2),0xbeef)

    def test_store_word_retains_unsigned_32_bits(self):
        regs=[0]*32;regs[8]=0x87654321
        trace,_=replay([op(43,5,8,4)],regs=regs)
        self.assertTrue(compare(trace,fixture((BASE,RAM+4,4,0x87654321)),guest_stopped_at_expected_pc=True)['matches_reference'])

    def test_all_three_store_widths_capture_precise_values(self):
        regs=[0]*32;regs[8]=0xabcdef12
        trace,_=replay([op(40,5,8,0),op(41,5,8,2),op(43,5,8,4)],regs=regs)
        r=compare(trace,fixture((BASE,RAM,1,0x12),
                                (BASE+4,RAM+2,2,0xef12),
                                (BASE+8,RAM+4,4,0xabcdef12)),guest_stopped_at_expected_pc=True)
        self.assertTrue(r['matches_reference'])
        self.assertEqual(r['executed_store_width_counts'],{'1':1,'2':1,'4':1})
        self.assertEqual(r['matching_event_count'],3)

    def test_same_value_store_detected_and_compared(self):
        regs=[0]*32;regs[8]=7
        trace,_=replay([op(40,5,8,0),op(40,5,8,0)],regs=regs)
        r=compare(trace,fixture((BASE,RAM,1,7),(BASE+4,RAM,1,0)),guest_stopped_at_expected_pc=True)
        self.assertEqual(r['value_mismatch_event_indices'],[1])
        self.assertFalse(r['matches_reference'])

    def test_transient_write_that_was_restored_is_detected(self):
        regs=[0]*32;regs[8]=77
        trace,mem=replay([op(40,5,8,0),op(40,5,0,0)],regs=regs)
        self.assertEqual(mem.read(RAM,1),0)
        r=compare(trace,fixture((BASE,RAM,1,78),(BASE+4,RAM,1,0)),guest_stopped_at_expected_pc=True)
        self.assertEqual(r['value_mismatch_event_indices'],[0])
        self.assertEqual(r['matching_event_count'],1)

    def test_old_gpr_stored_before_pending_load_retires(self):
        regs=[0]*32;regs[8]=0x12
        image=[op(40,5,8,0),op(40,5,8,1)]
        raw=struct.pack('<2I',*image)
        mem=MappedMemory().map_region(BASE,raw).map_region(RAM,bytes(16),writable=True)
        regs[5]=RAM
        trace=execute(raw,BASE,BASE,mem,regs,initial_pending_load=(8,0xabcdef34))
        self.assertEqual([v[-1] for v in trace['store_value_accesses']],[0x12,0x34])

    def test_failed_read_only_store_does_not_emit_value_event(self):
        raw=struct.pack('<I',op(41,5,8,0))
        regs=[0]*32;regs[5]=RAM;regs[8]=77
        mem=MappedMemory().map_region(BASE,raw).map_region(RAM,bytes(16))
        trace=execute(raw,BASE,BASE,mem,regs)
        self.assertEqual(trace['reason'],'ValueError')
        self.assertEqual(trace['store_value_accesses'],())

    def test_site_mismatch_distinguished_from_value_mismatch(self):
        regs=[0]*32;regs[8]=42
        trace,_=replay([op(40,5,8,0)],regs=regs)
        r=compare(trace,fixture((BASE,RAM+1,1,43)),guest_stopped_at_expected_pc=True)
        self.assertEqual(r['site_mismatch_event_indices'],[0])
        self.assertEqual(r['value_mismatch_event_indices'],[])

    def test_out_of_range_expected_value_must_not_be_silently_masked(self):
        for width,val in ((1,256),(2,65536),(4,0x100000000), (1,-1),(1,True)):
            obj={'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,
                                             'width':width,'value_u32':val}]}
            with self.subTest(width=width,val=val),self.assertRaises(ValueError):decode(obj)

    def test_decoder_accepts_exact_width_value_hex(self):
        x={'schema':SCHEMA,'events':[{'pc':hex(BASE),'address':hex(RAM),
                                     'width':2,'value_u32':'0x0000ffff'}]}
        self.assertEqual(decode(x),((BASE,RAM,2,0xffff),))

    def test_decoder_rejects_malformed_or_extra_fields(self):
        bad=[{}, {'schema':SCHEMA,'events':None},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,'width':1}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,'width':1,'value_u32':7,'secret':4}]},
             {'schema':SCHEMA,'events':[{'pc':BASE+2,'address':RAM,'width':1,'value_u32':4}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM+1,'width':4,'value_u32':4}]},
             {'schema':SCHEMA,'events':[{'pc':BASE,'address':RAM,'width':1,'value_u32':'7'}]}]
        for obj in bad:
            with self.subTest(obj=obj),self.assertRaises(ValueError):decode(obj)

    def test_project_sites_matches_legacy_site_only_log(self):
        x=fixture((BASE,RAM,1,7),(BASE+4,RAM+2,2,0xffff))
        self.assertEqual(project_sites(x),((BASE,RAM,1),(BASE+4,RAM+2,2)))

    def test_missing_trace_value_events_fail_closed(self):
        trace,_=replay([op(40,5,8,0)])
        del trace['store_value_accesses']
        with self.assertRaises(ValueError):trace_values(trace)

    def test_inconsistent_private_trace_source_register_rejected(self):
        trace,_=replay([op(40,5,8,0)])
        trace['store_value_accesses']=((BASE,RAM,1,9,0),)
        with self.assertRaises(ValueError):trace_values(trace)

    def test_out_of_range_private_trace_value_rejected(self):
        trace,_=replay([op(40,5,8,0)])
        trace['store_value_accesses']=((BASE,RAM,1,8,256),)
        with self.assertRaises(ValueError):trace_values(trace)

    def test_incomplete_run_withholds_value_mismatch_indices(self):
        trace,_=replay([op(40,5,8,0),op(40,5,8,1)],max_steps=1)
        r=compare(trace,fixture(),guest_stopped_at_expected_pc=False)
        self.assertFalse(r['comparison_performed'])
        self.assertEqual(r['value_mismatch_event_indices'],[])
        self.assertIsNone(r['matching_event_count'])

    def test_bounded_mismatch_indices_and_truncation(self):
        words=[op(40,5,8,i) for i in range(50)]
        trace,_=replay(words)
        r=compare(trace,fixture(),guest_stopped_at_expected_pc=True)
        self.assertEqual(len(r['mismatching_event_indices']),MAX_MISMATCH_INDICES)
        self.assertTrue(r['mismatch_indices_truncated'])

    def test_mismatch_report_never_prints_guest_data_or_digests(self):
        regs=[0]*32;regs[8]=0xdeadbeef
        trace,_=replay([op(43,5,8,0)],regs=regs)
        r=compare(trace,fixture((BASE,RAM,4,0x12345678)),guest_stopped_at_expected_pc=True)
        self.assertEqual(r['value_mismatch_event_indices'],[0])
        self.assertNotIn('deadbeef',str(r))
        self.assertNotIn(hex(RAM),str(r))
        self.assertNotIn(hex(BASE),str(r))
        self.assertFalse(r['private_values_emitted'])


if __name__ == '__main__':
    unittest.main()
