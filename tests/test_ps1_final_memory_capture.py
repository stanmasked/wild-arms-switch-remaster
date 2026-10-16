"""Full after-RAM fixture integration against synthetic PS-X EXE and CLI."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.mips_ps1_matrix_reference import compare
from tools.mips_ps1_capture_pack import pack
from tools.audit_ps1_capture_pack import main as pack_cli
from tools.audit_ps1_matrix_reference import main as verify_cli
from tools.mips_final_memory_state import pack as pack_ram
from tests.test_mips_ps1_matrix_reference import fixture, synthetic_program, op, BASE, MATRIX

SIZE=8192

def scene(*, side_effect=True):
    # Program writes 9 signed coefficients and, optionally, a byte in the
    # second 4-KiB block outside the 18-byte matrix.
    words=[op(9,0,8,4096)]+[op(41,5,8,2*i) for i in range(9)]
    if side_effect:
        words += [op(9,0,9,77),op(40,5,9,4100)]
    image=struct.pack('<%dI'%len(words),*words)
    head=bytearray(2048);head[:8]=b'PS-X EXE'
    struct.pack_into('<II',head,0x18,BASE,len(image))
    blob=bytes(head)+image
    b=bytes(SIZE);a=bytearray(b)
    for i in range(9):struct.pack_into('<h',a,i*2,4096)
    if side_effect:a[4100]=77
    before={'schema':'wild-arms-ps1-debugger-registers-v1','pc':BASE,
            'gpr':fixture(blob)['gpr'],'hi':0,'lo':0,
            'pending_load':None,'in_branch_delay_slot':False}
    after={'schema':'wild-arms-ps1-debugger-registers-v1','pc':BASE+len(image)}
    return blob,b,bytes(a),before,after


def reference(*, side_effect=True, strict=True):
    blob,b,a,reg_before,reg_after=scene(side_effect=side_effect)
    ref=pack(blob,reg_before,reg_after,b,a,ram_base=MATRIX,
             source='synthetic',require_final_memory_state=strict)
    return blob,ref

class FullMemoryCaptureTests(unittest.TestCase):
    def test_nine_matrix_coefficients_and_external_sb_both_verified(self):
        blob,ref=reference()
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['final_memory_state']['matches_reference'])
        self.assertEqual(result['final_memory_state']['checked_block_count'],2)
        self.assertEqual(result['final_memory_state']['expected_changed_bytes_outside_matrix'],1)
        self.assertEqual(result['final_memory_state']['observed_changed_bytes_outside_matrix'],1)
        self.assertTrue(result['matches_complete_reference'])

    def test_matrix_exact_but_expected_outside_sb_missing(self):
        blob,ref=reference(side_effect=False)
        # Claim another byte changed after capture, without changing the
        # actual guest program that only writes the matrix.
        _,b,a,_,_=scene(side_effect=False)
        changed=bytearray(a);changed[4100]=77
        ref['expected_final_memory_state']=pack_ram(b,bytes(changed),MATRIX,MATRIX)
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertEqual(result['final_memory_state']['mismatching_block_indices'],[1])
        self.assertFalse(result['final_memory_state']['matches_reference'])
        self.assertFalse(result['matches_complete_reference'])

    def test_matrix_exact_but_unexpected_external_write(self):
        blob,ref=reference(side_effect=True)
        _,b,a,_,_=scene(side_effect=True)
        changed=bytearray(a);changed[4100]=0
        ref['expected_final_memory_state']=pack_ram(b,bytes(changed),MATRIX,MATRIX)
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertFalse(result['matches_complete_reference'])
        self.assertEqual(result['final_memory_state']['observed_changed_bytes_outside_matrix'],1)
        self.assertEqual(result['final_memory_state']['expected_changed_bytes_outside_matrix'],0)

    def test_optional_mismatch_does_not_redefine_numeric_match(self):
        blob,ref=reference(side_effect=True)
        _,b,a,_,_=scene(side_effect=True)
        changed=bytearray(a);changed[4100]=0
        ref['expected_final_memory_state']=pack_ram(b,bytes(changed),MATRIX,MATRIX)
        ref['require_final_memory_state']=False
        result=compare(blob,ref)
        self.assertFalse(result['final_memory_state']['matches_reference'])
        self.assertTrue(result['matches_complete_reference'])

    def test_missing_required_memory_reference_fails_closed(self):
        blob,ref=reference()
        ref.pop('expected_final_memory_state')
        with self.assertRaisesRegex(ValueError,'strict final RAM comparison'):
            compare(blob,ref)

    def test_malformed_optional_reference_also_fails_closed(self):
        blob,ref=reference()
        ref['require_final_memory_state']=False
        ref['expected_final_memory_state']['block_sha256']=['malformed']
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_malformed_strict_flag_rejected(self):
        blob,ref=reference()
        ref['require_final_memory_state']=1
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_missing_mapped_before_ram_fails_without_filling_zeros(self):
        blob,ref=reference()
        # The matrix region itself is mapped but the second block is not.
        ref['memory_segments'][0]['data_hex']='00'*128
        with self.assertRaisesRegex(ValueError,'not fully mapped|unmapped gap'):
            compare(blob,ref)

    def test_step_limit_withholds_post_memory_evaluation(self):
        blob,ref=reference()
        ref['max_steps']=1
        r=compare(blob,ref)
        self.assertFalse(r['final_memory_state']['comparison_performed'])
        self.assertEqual(r['final_memory_state']['mismatching_block_indices'],[])
        self.assertFalse(r['matches_complete_reference'])

    def test_packer_skips_full_after_ram_evidence_when_not_requested(self):
        blob,b,a,before,after=scene()
        ref=pack(blob,before,after,b,a,ram_base=MATRIX,source='synthetic')
        self.assertNotIn('expected_final_memory_state',ref)
        self.assertFalse(ref['require_final_memory_state'])

    def test_packer_rejects_nonboolean_require_flag(self):
        blob,b,a,before,after=scene()
        with self.assertRaises(ValueError):
            pack(blob,before,after,b,a,ram_base=MATRIX,require_final_memory_state='yes')

    def test_combined_final_cpu_and_memory_verification(self):
        blob,b,a,before,after=scene()
        after['gpr']=list(before['gpr']);after['gpr'][8]=4096;after['gpr'][9]=77
        after.update({'hi':0,'lo':0,'pending_load':None,'in_branch_delay_slot':False})
        ref=pack(blob,before,after,b,a,ram_base=MATRIX,source='synthetic',
                 require_final_cpu_state=True,require_final_memory_state=True)
        r=compare(blob,ref)
        self.assertTrue(r['matches_complete_reference'])
        self.assertTrue(r['final_cpu_state']['final_cpu_state_matches_reference'])
        self.assertTrue(r['final_memory_state']['matches_reference'])

    def test_cli_pack_and_compare_full_ram(self):
        blob,b,a,before,after=scene()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);files=[root/n for n in ('exe','pre.json','post.json','pre.bin','post.bin','ref.json')]
            files[0].write_bytes(blob);files[1].write_text(json.dumps(before))
            files[2].write_text(json.dumps(after));files[3].write_bytes(b);files[4].write_bytes(a)
            args=['--exe',str(files[0]),'--before-registers',str(files[1]),
                  '--after-registers',str(files[2]),'--before-ram',str(files[3]),
                  '--after-ram',str(files[4]),'--ram-base',hex(MATRIX),
                  '--output',str(files[5]),'--require-final-memory-state',
                  '--compare','--synthetic']
            out=StringIO()
            with contextlib.redirect_stdout(out):status=pack_cli(args)
            self.assertEqual(status,0)
            report=json.loads(out.getvalue())
            self.assertTrue(report['final_memory_state']['matches_reference'])
            self.assertTrue(report['matches_complete_reference'])
            self.assertNotIn('block_sha256',out.getvalue())
            self.assertNotIn('77',out.getvalue())
            self.assertTrue(json.loads(files[5].read_text())['require_final_memory_state'])

    def test_numeric_cli_reports_memory_only_failure_as_exit_one(self):
        blob,ref=reference()
        _,b,a,_,_=scene()
        changed=bytearray(a);changed[4100]=0
        ref['expected_final_memory_state']=pack_ram(b,bytes(changed),MATRIX,MATRIX)
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'exe';capture=Path(td)/'ref.json'
            exe.write_bytes(blob);capture.write_text(json.dumps(ref))
            out=StringIO()
            with contextlib.redirect_stdout(out):status=verify_cli(['--exe',str(exe),'--reference',str(capture)])
            self.assertEqual(status,1)
            self.assertFalse(json.loads(out.getvalue())['matches_complete_reference'])

if __name__=='__main__':unittest.main()
