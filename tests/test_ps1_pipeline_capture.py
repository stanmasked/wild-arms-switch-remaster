"""External snapshot pipeline completeness, numeric comparison and packaging."""
import hashlib
import struct
import unittest
from tools.mips_ps1_matrix_reference import compare
from tools.mips_ps1_capture_pack import pack
from tests.test_mips_ps1_matrix_reference import fixture, op, BASE, MATRIX
from tests.test_mips_ps1_capture_pack import dumps


def synthetic_exe(words):
    head=bytearray(2048)
    head[:8]=b'PS-X EXE'
    payload=struct.pack('<%dI'%len(words),*words)
    struct.pack_into('<II',head,0x18,BASE,len(payload))
    return bytes(head)+payload


class PipelinedCaptureTests(unittest.TestCase):
    def test_explicit_pending_load_affects_nine_final_coefficients(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        snap=fixture(blob,source='external_ps1_capture_claim')
        snap['pending_load']={'gpr':8,'value_u32':4096}
        self.assertTrue(compare(blob,snap)['matches_supplied_nine_coefficients'])
        self.assertTrue(compare(blob,snap)['initial_pending_load_applied'])
        snap['pending_load']=None
        self.assertFalse(compare(blob,snap)['matches_supplied_nine_coefficients'])

    def test_first_sh_after_capture_uses_old_gpr_value(self):
        blob=synthetic_exe([op(41,5,8,0)]+[op(41,5,8,2*i) for i in range(1,9)])
        snap=fixture(blob,source='external_ps1_capture_claim',values=[0]+[4096]*8)
        snap['pending_load']={'gpr':8,'value_u32':4096}
        self.assertTrue(compare(blob,snap)['matches_supplied_nine_coefficients'])
        self.assertEqual(compare(blob,snap)['final_halfword_slots_written_by_sh'],9)

    def test_external_capture_requires_explicit_load_pipeline_state(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        ref=fixture(blob,source='external_ps1_capture_claim')
        del ref['pending_load']
        with self.assertRaisesRegex(ValueError,'pipeline'):
            compare(blob,ref)
        ref=fixture(blob,source='external_ps1_capture_claim')
        del ref['in_branch_delay_slot']
        with self.assertRaisesRegex(ValueError,'pipeline'):
            compare(blob,ref)

    def test_legacy_synthetic_fixture_defaults_to_no_pending_load(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        ref=fixture(blob)
        del ref['pending_load']
        del ref['in_branch_delay_slot']
        result=compare(blob,ref)
        self.assertFalse(result['initial_load_pipeline_state_explicit'])
        self.assertFalse(result['initial_pending_load_applied'])

    def test_branch_delay_slot_capture_must_be_rejected(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['in_branch_delay_slot']=True
        with self.assertRaisesRegex(ValueError,'control-flow delay slot'):
            compare(blob,ref)

    def test_pending_load_cannot_target_r0(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        ref=fixture(blob,source='external_ps1_capture_claim')
        for invalid in ({'gpr':0,'value_u32':1},{'gpr':32,'value_u32':1},
                        {'gpr':8,'value_u32':-1},{'gpr':8,'value_u32':True},
                        {'gpr':8,'value_u32':0x100000000},
                        {'gpr':8}, {'gpr':8,'value_u32':1,'secret':99},
                        [], 1):
            with self.subTest(value=invalid),self.assertRaises(ValueError):
                ref['pending_load']=invalid
                compare(blob,ref)

    def test_pipeline_boolean_requires_actual_boolean_type(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        ref=fixture(blob,source='external_ps1_capture_claim')
        for value in (0, 1, 'false', None, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ref['in_branch_delay_slot']=value
                compare(blob,ref)

    def test_capture_pack_forwards_explicit_pending_load(self):
        exe,r0,r1,before,after=dumps()
        r0['pending_load']={'gpr':8,'value_u32':'0x00001000'}
        result=pack(exe,r0,r1,before,after,ram_base=BASE,source='synthetic')
        self.assertEqual(result['pending_load'],r0['pending_load'])
        self.assertTrue(result['in_branch_delay_slot'] is False)
        self.assertTrue(compare(exe,result)['matches_supplied_nine_coefficients'])

    def test_capture_pack_rejects_unknown_pipeline_state(self):
        exe,r0,r1,before,after=dumps()
        del r0['pending_load']
        with self.assertRaisesRegex(ValueError,'pipeline'):
            pack(exe,r0,r1,before,after,ram_base=BASE)
        exe,r0,r1,before,after=dumps()
        del r0['in_branch_delay_slot']
        with self.assertRaisesRegex(ValueError,'pipeline'):
            pack(exe,r0,r1,before,after,ram_base=BASE)

    def test_capture_pack_refuses_control_delay_slot_and_invalid_values(self):
        exe,r0,r1,before,after=dumps()
        r0['in_branch_delay_slot']=True
        with self.assertRaises(ValueError):pack(exe,r0,r1,before,after,ram_base=BASE)
        exe,r0,r1,before,after=dumps()
        r0['pending_load']={'gpr':8,'value_u32':-1}
        with self.assertRaises(ValueError):pack(exe,r0,r1,before,after,ram_base=BASE)

    def test_privacy_does_not_emit_pending_load_content(self):
        blob=synthetic_exe([0]+[op(41,5,8,2*i) for i in range(9)])
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['pending_load']={'gpr':8,'value_u32':4096}
        summary=compare(blob,ref)
        self.assertNotIn('4096',str(summary))
        self.assertNotIn('value_u32',str(summary))
        self.assertTrue(summary['initial_pending_load_applied'])
        self.assertFalse(summary['private_values_emitted'])

if __name__=='__main__':unittest.main()
