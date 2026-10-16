"""Independent synthetic Q12 arithmetic capture with nine matrix coefficients."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.audit_ps1_capture_pack import main as pack_cli
from tools.audit_ps1_matrix_reference import main as verify_cli
from tools.mips_ps1_capture_pack import pack
from tools.mips_ps1_matrix_reference import compare
from tools.mips_arithmetic_event_sequence import SCHEMA
from tests.test_mips_ps1_matrix_reference import fixture, BASE, MATRIX, op


def reg(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn


def synthetic_builder(return_through_jr=False):
    instructions=[]
    events=[]
    for slot in range(9):
        parts = (reg(24,8,9),reg(18,rd=10),reg(3,rt=10,rd=11,sa=12),
                 reg(33,rs=11,rt=13,rd=12),op(41,5,12,slot*2))
        kinds = (('mult',0x200000,0),('mflo',0x200000,None),
                 ('sra',512,None),('addu',519,None))
        for j, w in enumerate(parts):
            pc=BASE + 4*len(instructions)
            instructions.append(w)
            if j < 4:
                kind,value,aux=kinds[j]
                events.append({'pc':pc,'kind':kind,
                               'result_u32':value,'secondary_u32':aux})
    if return_through_jr:
        instructions.append(reg(8,rs=31))
        pc=BASE+4*len(instructions)
        instructions.append(reg(33,rs=11,rt=13,rd=12))
        events.append({'pc':pc,'kind':'addu',
                       'result_u32':519,'secondary_u32':None})
    payload=struct.pack('<%dI'%len(instructions),*instructions)
    header=bytearray(2048);header[:8]=b'PS-X EXE'
    struct.pack_into('<II',header,0x18,BASE,len(payload))
    blob=bytes(header)+payload
    state=fixture(blob,values=[519]*9,source='synthetic')
    state['gpr'][8]=1024
    state['gpr'][9]=2048
    state['gpr'][13]=7
    if return_through_jr:
        state['gpr'][31]=BASE+len(payload)
    values={'schema':SCHEMA,'events':events}
    return blob,state,values


def capture_inputs(blob,reference):
    before={'schema':'wild-arms-ps1-debugger-registers-v1',
            'pc':BASE,'gpr':reference['gpr'],'hi':0,'lo':0,
            'pending_load':None,'in_branch_delay_slot':False}
    after={'schema':'wild-arms-ps1-debugger-registers-v1',
           'pc':reference['stop_pc']}
    pre=bytes(64)
    post=bytearray(pre)
    struct.pack_into('<9h',post,0,*([519]*9))
    return before,after,pre,bytes(post)


class CapturedArithmeticTests(unittest.TestCase):
    def test_nine_synthetic_q12_coefficients_and_36_intermediates_match(self):
        blob,ref,events=synthetic_builder()
        ref['expected_arithmetic_events']=events
        ref['require_arithmetic_events']=True
        out=compare(blob,ref)
        self.assertTrue(out['matches_complete_reference'])
        self.assertTrue(out['matches_supplied_nine_coefficients'])
        self.assertTrue(out['arithmetic_events']['matches_reference'])
        self.assertEqual(out['arithmetic_events']['matching_event_count'],36)
        self.assertEqual(out['arithmetic_events']['executed_kind_counts']['mult'],9)

    def test_bad_intermediate_value_does_not_require_wrong_final_matrix(self):
        blob,ref,events=synthetic_builder()
        ref['expected_arithmetic_events']=events
        ref['require_arithmetic_events']=True
        events['events'][10]['result_u32']=999
        out=compare(blob,ref)
        self.assertTrue(out['matches_supplied_nine_coefficients'])
        self.assertEqual(out['arithmetic_events']['result_value_mismatch_indices'],[10])
        self.assertFalse(out['matches_complete_reference'])

    def test_wrong_hi_part_detected_independently_of_product_low(self):
        blob,ref,events=synthetic_builder()
        events['events'][12]['secondary_u32']=123
        ref['expected_arithmetic_events']=events
        ref['require_arithmetic_events']=True
        out=compare(blob,ref)
        self.assertEqual(out['arithmetic_events']['secondary_result_mismatch_indices'],[12])
        self.assertTrue(out['matches_supplied_nine_coefficients'])
        self.assertFalse(out['matches_complete_reference'])

    def test_wrong_pc_or_kind_in_private_trace(self):
        blob,ref,events=synthetic_builder()
        events['events'][0]['kind']='multu'
        ref['expected_arithmetic_events']=events
        ref['require_arithmetic_events']=True
        out=compare(blob,ref)
        self.assertEqual(out['arithmetic_events']['opcode_or_pc_mismatch_indices'],[0])

    def test_optional_mismatch_reports_it_but_keeps_numeric_success(self):
        blob,ref,events=synthetic_builder()
        events['events'][4]['result_u32']=0
        ref['expected_arithmetic_events']=events
        out=compare(blob,ref)
        self.assertFalse(out['arithmetic_events']['matches_reference'])
        self.assertTrue(out['matches_complete_reference'])

    def test_missing_required_independent_debugger_log_fails_closed(self):
        blob,ref,_=synthetic_builder()
        ref['require_arithmetic_events']=True
        with self.assertRaisesRegex(ValueError,'independent arithmetic'):
            compare(blob,ref)

    def test_malformed_optional_debugger_arithmetic_log_fails_closed(self):
        blob,ref,events=synthetic_builder()
        events['events'][0]['result_u32']=-3
        ref['expected_arithmetic_events']=events
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_max_steps_prevents_mismatch_indices(self):
        blob,ref,events=synthetic_builder()
        ref['require_arithmetic_events']=True
        ref['expected_arithmetic_events']=events
        ref['max_steps']=5
        out=compare(blob,ref)
        self.assertFalse(out['arithmetic_events']['comparison_performed'])
        self.assertEqual(out['arithmetic_events']['mismatching_event_indices'],[])
        self.assertFalse(out['matches_complete_reference'])

    def test_completed_jr_ra_delay_slot_arithmetic_event(self):
        blob,ref,events=synthetic_builder(return_through_jr=True)
        ref['expected_arithmetic_events']=events
        ref['require_arithmetic_events']=True
        ref['require_completed_jr_ra']=True
        out=compare(blob,ref)
        self.assertTrue(out['return_boundary']['verified_complete_jr_ra_return'])
        self.assertTrue(out['matches_complete_reference'])
        self.assertEqual(out['arithmetic_events']['executed_event_count'],37)

    def test_packer_carries_private_log_without_fabrication(self):
        blob,ref,events=synthetic_builder()
        before,after,ram0,ram1=capture_inputs(blob,ref)
        p=pack(blob,before,after,ram0,ram1,ram_base=MATRIX,
               source='synthetic',arithmetic_events=events,
               require_arithmetic_events=True)
        self.assertTrue(compare(blob,p)['matches_complete_reference'])
        self.assertEqual(p['expected_arithmetic_events'],events)
        default=pack(blob,before,after,ram0,ram1,ram_base=MATRIX)
        self.assertNotIn('expected_arithmetic_events',default)

    def test_packer_missing_strict_log_is_rejected(self):
        blob,ref,_=synthetic_builder()
        before,after,ram0,ram1=capture_inputs(blob,ref)
        with self.assertRaisesRegex(ValueError,'independent debugger arithmetic'):
            pack(blob,before,after,ram0,ram1,ram_base=MATRIX,
                 require_arithmetic_events=True)

    def test_packer_non_boolean_strict_flag_is_rejected(self):
        blob,ref,events=synthetic_builder()
        before,after,ram0,ram1=capture_inputs(blob,ref)
        with self.assertRaises(ValueError):
            pack(blob,before,after,ram0,ram1,ram_base=MATRIX,
                 arithmetic_events=events,require_arithmetic_events='yes')

    def test_pack_cli_strict_arithmetic_log_roundtrip(self):
        blob,ref,events=synthetic_builder()
        before,after,ram0,ram1=capture_inputs(blob,ref)
        with tempfile.TemporaryDirectory() as temp:
            files=[Path(temp)/n for n in ('image.exe','pre.json','post.json',
                                         'pre.ram','post.ram','arith.json','snapshot.json')]
            files[0].write_bytes(blob)
            files[1].write_text(json.dumps(before))
            files[2].write_text(json.dumps(after))
            files[3].write_bytes(ram0)
            files[4].write_bytes(ram1)
            files[5].write_text(json.dumps(events))
            args=['--exe',str(files[0]),'--before-registers',str(files[1]),
                  '--after-registers',str(files[2]),'--before-ram',str(files[3]),
                  '--after-ram',str(files[4]),'--ram-base',hex(MATRIX),
                  '--arithmetic-events',str(files[5]),'--require-arithmetic-events',
                  '--output',str(files[6]),'--synthetic','--compare']
            output=StringIO()
            with contextlib.redirect_stdout(output): status=pack_cli(args)
            self.assertEqual(status,0)
            published=json.loads(output.getvalue())
            self.assertTrue(published['arithmetic_events']['matches_reference'])
            self.assertNotIn('0x8001',output.getvalue())
            self.assertNotIn('result_u32',output.getvalue())
            private=json.loads(files[6].read_text())
            self.assertTrue(private['require_arithmetic_events'])
            self.assertEqual(len(private['expected_arithmetic_events']['events']),36)

    def test_private_reference_cli_reports_value_only_mismatch_as_failure(self):
        blob,ref,events=synthetic_builder()
        events['events'][8]['result_u32']=1
        ref['expected_arithmetic_events']=events
        ref['require_arithmetic_events']=True
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'exe';jsonfile=Path(temp)/'capture.json'
            exe.write_bytes(blob);jsonfile.write_text(json.dumps(ref))
            output=StringIO()
            with contextlib.redirect_stdout(output):
                result=verify_cli(['--exe',str(exe),'--reference',str(jsonfile)])
            self.assertEqual(result,1)
            safe=json.loads(output.getvalue())
            self.assertTrue(safe['matches_supplied_nine_coefficients'])
            self.assertFalse(safe['matches_complete_reference'])

    def test_cli_requires_real_separate_log_not_guess_from_ram(self):
        blob,ref,_=synthetic_builder()
        before,after,ram0,ram1=capture_inputs(blob,ref)
        with tempfile.TemporaryDirectory() as temp:
            files=[Path(temp)/n for n in ('exe','before','after','ram0','ram1','out')]
            files[0].write_bytes(blob);files[1].write_text(json.dumps(before))
            files[2].write_text(json.dumps(after));files[3].write_bytes(ram0)
            files[4].write_bytes(ram1)
            args=['--exe',str(files[0]),'--before-registers',str(files[1]),
                  '--after-registers',str(files[2]),'--before-ram',str(files[3]),
                  '--after-ram',str(files[4]),'--ram-base',hex(MATRIX),
                  '--require-arithmetic-events','--output',str(files[5]),'--synthetic']
            output=StringIO()
            with contextlib.redirect_stdout(output):status=pack_cli(args)
            self.assertEqual(status,2)
            self.assertFalse(files[5].exists())

if __name__ == '__main__':unittest.main()
