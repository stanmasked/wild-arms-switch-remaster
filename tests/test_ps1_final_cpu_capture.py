"""Independent synthetic coefficient and post-return R3000A state integration."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tools.mips_ps1_matrix_reference import compare
from tools.mips_ps1_capture_pack import pack
from tools.audit_ps1_capture_pack import main as pack_cli
from tools.audit_ps1_matrix_reference import main as compare_cli
from tests.test_mips_ps1_matrix_reference import synthetic_program, fixture, op, BASE, MATRIX
from tests.test_mips_ps1_capture_pack import dumps


def cpu_fixture(blob=None):
    blob=synthetic_program() if blob is None else blob
    ref=fixture(blob,source='external_ps1_capture_claim')
    ref['require_final_cpu_state']=True
    gpr=list(ref['gpr']);gpr[8]=4096
    ref['expected_final_cpu_state']={
        'gpr':gpr,'hi':0,'lo':0,
        'pending_load':None,'in_branch_delay_slot':False}
    return blob,ref


class FinalCPUIntegrationTests(unittest.TestCase):
    def test_strict_complete_cpu_and_matrix_match(self):
        blob,ref=cpu_fixture()
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['final_cpu_state']['final_cpu_state_matches_reference'])
        self.assertTrue(result['matches_complete_reference'])
        self.assertTrue(result['strict_final_cpu_state_required'])

    def test_numeric_matches_but_final_gpr_does_not(self):
        blob,ref=cpu_fixture()
        ref['expected_final_cpu_state']['gpr'][8]=17
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertFalse(result['matches_complete_reference'])
        self.assertEqual(result['final_cpu_state']['mismatching_gpr_indices'],[8])

    def test_numeric_matches_but_hi_mismatch(self):
        blob,ref=cpu_fixture()
        ref['expected_final_cpu_state']['hi']=0x87654321
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertFalse(result['matches_complete_reference'])
        self.assertFalse(result['final_cpu_state']['hi_matches_reference'])
        self.assertNotIn('87654321',str(result))

    def test_numeric_matches_but_lo_mismatch(self):
        blob,ref=cpu_fixture()
        ref['expected_final_cpu_state']['lo']=12345
        result=compare(blob,ref)
        self.assertFalse(result['matches_complete_reference'])
        self.assertFalse(result['final_cpu_state']['lo_matches_reference'])

    def test_numeric_matches_but_pending_load_mismatch(self):
        blob,ref=cpu_fixture()
        ref['expected_final_cpu_state']['pending_load']={'gpr':10,'value_u32':4096}
        result=compare(blob,ref)
        self.assertFalse(result['matches_complete_reference'])
        self.assertFalse(result['final_cpu_state']['pending_load_matches_reference'])
        self.assertNotIn('4096',str(result['final_cpu_state']))

    def test_unrequested_state_comparison_does_not_block_numeric(self):
        blob,ref=cpu_fixture()
        ref['require_final_cpu_state']=False
        ref['expected_final_cpu_state']['gpr'][8]=4
        result=compare(blob,ref)
        self.assertTrue(result['matches_complete_reference'])
        self.assertFalse(result['final_cpu_state']['final_cpu_state_matches_reference'])

    def test_strict_state_missing_fails_not_implicitly_assumed(self):
        blob,ref=cpu_fixture()
        del ref['expected_final_cpu_state']
        with self.assertRaisesRegex(ValueError,'complete post-return state'):
            compare(blob,ref)

    def test_invalid_final_state_still_rejected_even_when_not_strict(self):
        blob,ref=cpu_fixture()
        ref['require_final_cpu_state']=False
        ref['expected_final_cpu_state']['gpr']=[]
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_strict_requirement_not_boolean_rejected(self):
        blob,ref=cpu_fixture()
        for value in (1,'true',None):
            ref['require_final_cpu_state']=value
            with self.subTest(value=value),self.assertRaises(ValueError):compare(blob,ref)

    def test_missing_final_guest_stop_prevents_post_cpu_comparison(self):
        blob,ref=cpu_fixture()
        ref['max_steps']=1
        result=compare(blob,ref)
        self.assertFalse(result['matches_complete_reference'])
        self.assertFalse(result['final_cpu_state']['final_cpu_state_comparison_performed'])
        self.assertIsNone(result['final_cpu_state']['hi_matches_reference'])

    def test_pack_requires_full_after_state_only_in_strict_mode(self):
        exe,before,after,ram0,ram1=dumps()
        with self.assertRaises(ValueError):
            pack(exe,before,after,ram0,ram1,ram_base=BASE,require_final_cpu_state=True)
        packed=pack(exe,before,after,ram0,ram1,ram_base=BASE)
        self.assertNotIn('expected_final_cpu_state',packed)
        self.assertFalse(packed['require_final_cpu_state'])

    def test_pack_and_compare_full_after_state(self):
        exe,before,after,ram0,ram1=dumps()
        after['gpr']=list(before['gpr']);after['gpr'][8]=4096
        after.update({'hi':0,'lo':0,'pending_load':None,'in_branch_delay_slot':False})
        packed=pack(exe,before,after,ram0,ram1,ram_base=BASE,require_final_cpu_state=True)
        self.assertTrue(compare(exe,packed)['matches_complete_reference'])

    def test_pack_partial_after_registers_rejected(self):
        exe,before,after,ram0,ram1=dumps()
        after['gpr']=list(before['gpr'])
        with self.assertRaises(ValueError):
            pack(exe,before,after,ram0,ram1,ram_base=BASE)

    def test_pack_after_branch_slot_rejected(self):
        exe,before,after,ram0,ram1=dumps()
        after['gpr']=list(before['gpr']);after['gpr'][8]=4096
        after.update({'hi':0,'lo':0,'pending_load':None,'in_branch_delay_slot':True})
        with self.assertRaises(ValueError):
            pack(exe,before,after,ram0,ram1,ram_base=BASE,require_final_cpu_state=True)

    def test_pack_cli_full_post_cpu_state_option(self):
        exe,before,after,ram0,ram1=dumps()
        after['gpr']=list(before['gpr']);after['gpr'][8]=4096
        after.update({'hi':0,'lo':0,'pending_load':None,'in_branch_delay_slot':False})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            filenames=[root/s for s in ('exe','before.json','after.json','before.bin','after.bin','out.json')]
            filenames[0].write_bytes(exe)
            filenames[1].write_text(json.dumps(before))
            filenames[2].write_text(json.dumps(after))
            filenames[3].write_bytes(ram0)
            filenames[4].write_bytes(ram1)
            args=['--exe',str(filenames[0]),'--before-registers',str(filenames[1]),
                  '--after-registers',str(filenames[2]),'--before-ram',str(filenames[3]),
                  '--after-ram',str(filenames[4]),'--ram-base',hex(BASE),
                  '--output',str(filenames[5]),'--require-final-cpu-state','--compare']
            out=StringIO()
            with contextlib.redirect_stdout(out):rc=pack_cli(args)
            self.assertEqual(rc,0)
            report=json.loads(out.getvalue())
            self.assertTrue(report['matches_complete_reference'])
            self.assertNotIn('4096',out.getvalue())
            self.assertEqual(json.loads(filenames[5].read_text())['require_final_cpu_state'],True)

    def test_reference_cli_returns_failure_for_cpu_only_mismatch(self):
        blob,ref=cpu_fixture()
        ref['expected_final_cpu_state']['gpr'][8]=3
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'image.exe';data=Path(folder)/'ref.json'
            exe.write_bytes(blob);data.write_text(json.dumps(ref))
            out=StringIO()
            with contextlib.redirect_stdout(out):
                rc=compare_cli(['--exe',str(exe),'--reference',str(data)])
            self.assertEqual(rc,1)
            self.assertTrue(json.loads(out.getvalue())['matches_supplied_nine_coefficients'])
            self.assertFalse(json.loads(out.getvalue())['matches_complete_reference'])

    def test_independent_mult_hilo_final_cpu_state(self):
        # Nine stores of 4096; then signed MULT t0,t1 and MFLO t2.
        code=[op(9,0,8,4096)]+[op(41,5,8,2*i) for i in range(9)]
        code += [op(9,0,9,7),(8<<21)|(9<<16)|24,(10<<11)|18]
        import struct
        image=struct.pack('<%dI'%len(code),*code)
        header=bytearray(2048);header[:8]=b'PS-X EXE'
        struct.pack_into('<II',header,0x18,BASE,len(image))
        blob=bytes(header)+image
        _,ref=cpu_fixture(blob)
        ref['expected_final_cpu_state']['gpr'][9]=7
        ref['expected_final_cpu_state']['gpr'][10]=28672
        ref['expected_final_cpu_state']['lo']=28672
        self.assertTrue(compare(blob,ref)['matches_complete_reference'])

if __name__=='__main__':unittest.main()
