"""Private value-aware store-event capture and comparison integration."""
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
from tools.mips_store_value_sequence import SCHEMA
from tests.test_mips_ps1_matrix_reference import BASE, MATRIX, fixture, synthetic_program, op
from tests.test_mips_ps1_capture_pack import dumps


def expected(blob, *, matrix=MATRIX, expected_value=4096):
    return {'schema':SCHEMA,'events':[
        {'pc':BASE + 4*(i+1), 'address':matrix+2*i,
         'width':2,'value_u32':expected_value}
        for i in range(9)]}


class StoreValueReferenceTests(unittest.TestCase):
    def test_nine_exact_sh_value_events_match_independent_fixture(self):
        blob=synthetic_program()
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['expected_store_values']=expected(blob)
        ref['require_store_values']=True
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['store_values']['matches_reference'])
        self.assertTrue(result['matches_complete_reference'])
        self.assertEqual(result['store_values']['matching_event_count'],9)

    def test_wrong_value_event_blocks_full_result_not_numeric_matrix(self):
        blob=synthetic_program()
        ref=fixture(blob)
        seq=expected(blob);seq['events'][4]['value_u32']=42
        ref['expected_store_values']=seq
        ref['require_store_values']=True
        r=compare(blob,ref)
        self.assertTrue(r['matches_supplied_nine_coefficients'])
        self.assertFalse(r['matches_complete_reference'])
        self.assertEqual(r['store_values']['value_mismatch_event_indices'],[4])

    def test_value_mismatch_optional_does_not_override_nine_coefficients(self):
        blob=synthetic_program();ref=fixture(blob)
        seq=expected(blob);seq['events'][4]['value_u32']=42
        ref['expected_store_values']=seq
        r=compare(blob,ref)
        self.assertTrue(r['matches_complete_reference'])
        self.assertFalse(r['store_values']['matches_reference'])

    def test_two_equal_sh_writes_are_distinct_even_if_final_value_same(self):
        # addiu r8,4096; SH to first slot twice; write the remaining eight
        words=[op(9,0,8,4096),op(41,5,8,0),op(41,5,8,0)]
        words.extend(op(41,5,8,2*i) for i in range(1,9))
        image=struct.pack('<%dI'%len(words),*words)
        header=bytearray(2048);header[:8]=b'PS-X EXE'
        struct.pack_into('<II',header,0x18,BASE,len(image))
        blob=bytes(header)+image
        ref=fixture(blob)
        ref['require_store_values']=True
        ref['expected_store_values']=expected(blob)
        r=compare(blob,ref)
        self.assertTrue(r['matches_supplied_nine_coefficients'])
        self.assertFalse(r['matches_complete_reference'])
        self.assertEqual(r['store_values']['executed_store_count'],10)

    def test_missing_required_independent_values_refused(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['require_store_values']=True
        with self.assertRaisesRegex(ValueError,'independent store-value'):
            compare(blob,ref)

    def test_malformed_optional_value_fixture_refused(self):
        blob=synthetic_program();ref=fixture(blob)
        seq=expected(blob);seq['events'][1]['value_u32']=65536
        ref['expected_store_values']=seq
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_combined_site_log_and_value_log_must_not_conflict(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['expected_store_values']=expected(blob)
        sites=[{k:ev[k] for k in ('pc','address','width')}
               for ev in ref['expected_store_values']['events']]
        ref['expected_store_sequence']={'schema':'wild-arms-ps1-store-sequence-v1',
                                        'events':sites}
        self.assertTrue(compare(blob,ref)['store_values']['matches_reference'])
        ref['expected_store_sequence']['events'][2]['address']=MATRIX+10
        with self.assertRaisesRegex(ValueError,'conflicting'):compare(blob,ref)

    def test_unfinished_guest_does_not_publish_value_mismatch_positions(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['expected_store_values']=expected(blob)
        ref['max_steps']=2
        r=compare(blob,ref)
        self.assertFalse(r['store_values']['comparison_performed'])
        self.assertEqual(r['store_values']['value_mismatch_event_indices'],[])

    def test_capture_pack_uses_private_log_without_inventing_it(self):
        blob,before,after,ram0,ram1=dumps()
        data=pack(blob,before,after,ram0,ram1,ram_base=BASE,
                  store_values=expected(blob,matrix=before['gpr'][5]),
                  require_store_values=True,source='synthetic')
        self.assertTrue(data['require_store_values'])
        self.assertTrue(compare(blob,data)['matches_complete_reference'])
        without=pack(blob,before,after,ram0,ram1,ram_base=BASE)
        self.assertNotIn('expected_store_values',without)

    def test_packer_refuses_strict_mode_without_external_value_log(self):
        blob,before,after,ram0,ram1=dumps()
        with self.assertRaisesRegex(ValueError,'missing independent'):
            pack(blob,before,after,ram0,ram1,ram_base=BASE,
                 require_store_values=True)

    def test_packer_refuses_conflicting_site_and_value_logs(self):
        blob,before,after,ram0,ram1=dumps()
        e=expected(blob,matrix=before['gpr'][5])
        sites=[{k:v[k] for k in ('pc','address','width')} for v in e['events']]
        sites[1]['address']+=2
        with self.assertRaises(ValueError):
            pack(blob,before,after,ram0,ram1,ram_base=BASE,
                 store_values=e,store_sequence={'schema':'wild-arms-ps1-store-sequence-v1',
                                                'events':sites})

    def test_strict_flag_must_be_actual_boolean(self):
        blob,before,after,ram0,ram1=dumps()
        with self.assertRaises(ValueError):
            pack(blob,before,after,ram0,ram1,ram_base=BASE,
                 require_store_values='yes')

    def test_cli_private_value_file_complete_reference(self):
        blob,before,after,ram0,ram1=dumps()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            paths=[root/x for x in ('EXE','pre.json','post.json','pre.bin',
                                     'post.bin','store-values.json','ref.json')]
            paths[0].write_bytes(blob)
            paths[1].write_text(json.dumps(before))
            paths[2].write_text(json.dumps(after))
            paths[3].write_bytes(ram0)
            paths[4].write_bytes(ram1)
            paths[5].write_text(json.dumps(expected(blob,matrix=before['gpr'][5])))
            args=['--exe',str(paths[0]),'--before-registers',str(paths[1]),
                  '--after-registers',str(paths[2]),'--before-ram',str(paths[3]),
                  '--after-ram',str(paths[4]),'--ram-base',hex(BASE),
                  '--store-value-events',str(paths[5]),'--require-store-values',
                  '--output',str(paths[6]),'--synthetic','--compare']
            stdout=StringIO()
            with contextlib.redirect_stdout(stdout):rc=pack_cli(args)
            r=json.loads(stdout.getvalue())
            self.assertEqual(rc,0)
            self.assertTrue(r['store_values']['matches_reference'])
            self.assertTrue(json.loads(paths[6].read_text())['require_store_values'])
            self.assertNotIn('4096',stdout.getvalue())
            self.assertNotIn(hex(MATRIX),stdout.getvalue())
            self.assertNotIn('value_u32',stdout.getvalue())

    def test_verifier_cli_returns_one_on_value_only_failure(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['require_store_values']=True
        seq=expected(blob);seq['events'][3]['value_u32']=1
        ref['expected_store_values']=seq
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'exe';capture=Path(temp)/'ref.json'
            exe.write_bytes(blob);capture.write_text(json.dumps(ref))
            stdout=StringIO()
            with contextlib.redirect_stdout(stdout):rc=verify_cli(['--exe',str(exe),'--reference',str(capture)])
            self.assertEqual(rc,1)
            out=json.loads(stdout.getvalue())
            self.assertTrue(out['matches_supplied_nine_coefficients'])
            self.assertFalse(out['matches_complete_reference'])
            self.assertNotIn('value_u32',stdout.getvalue())

    def test_cli_missing_required_file_does_not_create_private_reference(self):
        blob,before,after,ram0,ram1=dumps()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            files=[root/x for x in ('exe','pre','post','b','a','ref')]
            files[0].write_bytes(blob);files[1].write_text(json.dumps(before))
            files[2].write_text(json.dumps(after));files[3].write_bytes(ram0)
            files[4].write_bytes(ram1)
            args=['--exe',str(files[0]),'--before-registers',str(files[1]),
                  '--after-registers',str(files[2]),'--before-ram',str(files[3]),
                  '--after-ram',str(files[4]),'--ram-base',hex(BASE),
                  '--require-store-values','--output',str(files[5]),'--synthetic']
            stdout=StringIO()
            with contextlib.redirect_stdout(stdout):rc=pack_cli(args)
            self.assertEqual(rc,2)
            self.assertFalse(files[5].exists())
            self.assertNotIn(hex(MATRIX),stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
