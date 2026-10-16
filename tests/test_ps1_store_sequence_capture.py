"""Complete store-event log is separate from the before/after RAM capture."""
import contextlib
import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools.mips_ps1_matrix_reference import compare
from tools.mips_ps1_capture_pack import pack
from tools.audit_ps1_capture_pack import main
from tools.mips_store_event_sequence import SCHEMA
from tests.test_mips_ps1_matrix_reference import synthetic_program,fixture,op,BASE,MATRIX
from tests.test_mips_ps1_capture_pack import dumps


def events(blob, matrix=MATRIX):
    # The artificial, known straight-line program is encoded solely by this
    # test helper, not inferred by the actual packer from before/after RAM.
    words=len(blob[2048:])//4
    return {'schema':SCHEMA,'events':[
        {'pc':BASE+4*(1+i),'address':matrix+2*i,'width':2}
        for i in range(words-1)]}


class StoreCaptureIntegrationTests(unittest.TestCase):
    def test_all_nine_sh_events_can_be_checked_separately_from_matrix(self):
        blob=synthetic_program()
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['expected_store_sequence']=events(blob)
        ref['require_store_sequence']=True
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['store_sequence']['matches_reference'])
        self.assertTrue(result['matches_complete_reference'])
        self.assertEqual(result['store_sequence']['executed_store_width_counts']['2'],9)

    def test_omitted_same_value_store_detected_even_if_nine_coefficients_match(self):
        blob=synthetic_program()
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['expected_store_sequence']=events(blob)
        ref['expected_store_sequence']['events'].pop(5)
        ref['require_store_sequence']=True
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertFalse(result['matches_complete_reference'])
        self.assertEqual(result['store_sequence']['mismatching_event_indices'],[5,6,7,8])

    def test_optional_store_mismatch_does_not_override_matrix_only_result(self):
        blob=synthetic_program()
        ref=fixture(blob)
        ref['expected_store_sequence']={'schema':SCHEMA,'events':[]}
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['matches_complete_reference'])
        self.assertFalse(result['store_sequence']['matches_reference'])

    def test_strict_missing_store_log_is_invalid_not_empty(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['require_store_sequence']=True
        with self.assertRaisesRegex(ValueError,'debugger event log'):
            compare(blob,ref)

    def test_malformed_optional_store_log_rejected(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['expected_store_sequence']={'schema':SCHEMA,'events':[{'pc':BASE}]}
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_wrong_width_can_be_detected_when_ram_matches(self):
        blob=synthetic_program();ref=fixture(blob)
        seq=events(blob)
        seq['events'][0]['width']=1
        ref['expected_store_sequence']=seq
        ref['require_store_sequence']=True
        r=compare(blob,ref)
        self.assertEqual(r['store_sequence']['mismatching_event_indices'],[0])
        self.assertFalse(r['matches_complete_reference'])

    def test_replay_step_limit_withholds_store_mismatch_positions(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['expected_store_sequence']=events(blob)
        ref['require_store_sequence']=True
        ref['max_steps']=2
        r=compare(blob,ref)
        self.assertFalse(r['store_sequence']['comparison_performed'])
        self.assertEqual(r['store_sequence']['mismatching_event_indices'],[])
        self.assertFalse(r['matches_complete_reference'])

    def test_pack_refuses_mandatory_trace_if_no_log_supplied(self):
        exe,pre,post,ram0,ram1=dumps()
        with self.assertRaisesRegex(ValueError,'missing debugger store-event'):
            pack(exe,pre,post,ram0,ram1,ram_base=BASE,
                 require_store_sequence=True)

    def test_pack_carries_external_log_without_inventing_it(self):
        exe,pre,post,ram0,ram1=dumps()
        data=pack(exe,pre,post,ram0,ram1,ram_base=BASE,
                  store_sequence=events(exe,pre['gpr'][5]),require_store_sequence=True)
        self.assertTrue(data['require_store_sequence'])
        self.assertEqual(data['expected_store_sequence'],events(exe,pre['gpr'][5]))
        self.assertTrue(compare(exe,data)['matches_complete_reference'])
        no_log=pack(exe,pre,post,ram0,ram1,ram_base=BASE)
        self.assertNotIn('expected_store_sequence',no_log)

    def test_capture_pack_rejects_strict_non_boolean(self):
        exe,pre,post,ram0,ram1=dumps()
        with self.assertRaises(ValueError):pack(exe,pre,post,ram0,ram1,ram_base=BASE,
                                                require_store_sequence='yes')

    def test_cli_consumes_external_event_file_and_keeps_private_values_off_stdout(self):
        exe,pre,post,ram0,ram1=dumps()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            paths=[root/name for name in ('exe','pre.json','post.json','pre.bin',
                                         'post.bin','events.json','capture.json')]
            paths[0].write_bytes(exe)
            paths[1].write_text(json.dumps(pre));paths[2].write_text(json.dumps(post))
            paths[3].write_bytes(ram0);paths[4].write_bytes(ram1)
            paths[5].write_text(json.dumps(events(exe,pre['gpr'][5])))
            args=['--exe',str(paths[0]),'--before-registers',str(paths[1]),
                  '--after-registers',str(paths[2]),'--before-ram',str(paths[3]),
                  '--after-ram',str(paths[4]),'--ram-base',hex(BASE),
                  '--store-events',str(paths[5]),'--require-store-sequence',
                  '--output',str(paths[6]),'--compare','--synthetic']
            stdout=StringIO()
            with contextlib.redirect_stdout(stdout): rc=main(args)
            result=json.loads(stdout.getvalue())
            self.assertEqual(rc,0)
            self.assertTrue(result['matches_complete_reference'])
            self.assertTrue(result['store_sequence']['matches_reference'])
            self.assertNotIn(hex(MATRIX),stdout.getvalue())
            self.assertNotIn('event_address',stdout.getvalue())
            self.assertTrue(json.loads(paths[6].read_text())['require_store_sequence'])

    def test_cli_without_event_file_must_not_fabricate_trace(self):
        exe,pre,post,ram0,ram1=dumps()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);files=[root/s for s in ('exe','pre','post','ram0','ram1','out')]
            files[0].write_bytes(exe);files[1].write_text(json.dumps(pre))
            files[2].write_text(json.dumps(post))
            files[3].write_bytes(ram0);files[4].write_bytes(ram1)
            args=['--exe',str(files[0]),'--before-registers',str(files[1]),
                  '--after-registers',str(files[2]),'--before-ram',str(files[3]),
                  '--after-ram',str(files[4]),'--ram-base',hex(BASE),
                  '--output',str(files[5]),'--require-store-sequence','--synthetic']
            stdout=StringIO()
            with contextlib.redirect_stdout(stdout):rc=main(args)
            self.assertEqual(rc,2)
            self.assertFalse(files[5].exists())

    def test_jr_delay_slot_store_is_in_complete_guest_sequence(self):
        # Ninth SH is in the return delay slot; its program counter must
        # remain visible in the *private* trace while the public report hides it.
        from tests.test_ps1_reference_return_boundary import return_capture
        blob,ref=return_capture()
        seq={'schema':SCHEMA,'events':[
            {'pc':BASE+4*(1+i),'address':MATRIX+2*i,'width':2}
            for i in range(8)] +
            [{'pc':BASE+4*10,'address':MATRIX+16,'width':2}]}
        ref['expected_store_sequence']=seq
        ref['require_store_sequence']=True
        r=compare(blob,ref)
        self.assertTrue(r['matches_complete_reference'])
        self.assertEqual(r['store_sequence']['executed_store_count'],9)


if __name__=='__main__': unittest.main()
