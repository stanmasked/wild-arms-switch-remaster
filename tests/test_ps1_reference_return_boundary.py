"""Strict returned-to-caller boundary as an opt-in private PS1 comparison gate."""
import json
import struct
import tempfile
from pathlib import Path
import unittest

from tools.mips_ps1_matrix_reference import compare
from tools.mips_ps1_capture_pack import pack
from tools.audit_ps1_capture_pack import main
from tests.test_mips_ps1_matrix_reference import fixture, synthetic_program
from tests.test_mips_ps1_capture_pack import dumps, BASE


def op(code,rs=0,rt=0,imm=0):
    return (code<<26)|(rs<<21)|(rt<<16)|(imm&65535)


def synthetic_exe(words):
    image=struct.pack('<%dI'%len(words),*words)
    header=bytearray(2048)
    header[:8]=b'PS-X EXE'
    struct.pack_into('<II',header,0x18,BASE,len(image))
    return bytes(header)+image


def jr(rs=31):
    return (rs<<21)|8


def return_capture(*, return_kind='jr_ra', bad_delay_slot=False, source='external_ps1_capture_claim'):
    words=[op(9,0,8,4096)] + [op(41,5,8,i*2) for i in range(8)]
    if return_kind=='jr_ra':
        words.append(jr())
    elif return_kind=='jr_t0':
        words.append(jr(9))
    elif return_kind=='jalr':
        words.append((9<<21)|(30<<11)|9)
    else:
        words.append(0)
    words.append(18<<26 if bad_delay_slot else op(41,5,8,16))
    blob=synthetic_exe(words)
    ref=fixture(blob,source=source)
    ref['gpr'][31]=BASE+4*len(words)
    ref['gpr'][9]=BASE+4*len(words)
    ref['require_completed_jr_ra']=True
    return blob,ref


class StrictReferenceReturnTests(unittest.TestCase):
    def test_jr_ra_delay_slot_final_matrix_sh_numeric_match(self):
        blob,ref=return_capture()
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['strict_jr_ra_return_required'])
        self.assertTrue(result['return_boundary']['verified_complete_jr_ra_return'])
        self.assertTrue(result['coefficient_comparison_performed'])

    def test_complete_nine_sh_without_jr_rejected_in_strict_mode(self):
        blob=synthetic_program()
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['require_completed_jr_ra']=True
        result=compare(blob,ref)
        self.assertTrue(result['guest_completed_at_expected_stop'])
        self.assertTrue(result['all_nine_final_sh_verified'])
        self.assertFalse(result['coefficient_comparison_performed'])
        self.assertFalse(result['matches_supplied_nine_coefficients'])

    def test_legacy_nine_sh_without_return_still_accepted_without_strict_opt_in(self):
        blob=synthetic_program()
        ref=fixture(blob,source='synthetic')
        result=compare(blob,ref)
        self.assertFalse(result['strict_jr_ra_return_required'])
        self.assertTrue(result['matches_supplied_nine_coefficients'])

    def test_jr_t0_does_not_count_as_jr_ra(self):
        blob,ref=return_capture(return_kind='jr_t0')
        result=compare(blob,ref)
        self.assertFalse(result['return_boundary']['verified_complete_jr_ra_return'])
        self.assertFalse(result['coefficient_comparison_performed'])

    def test_jalr_does_not_count_as_jr_ra(self):
        blob,ref=return_capture(return_kind='jalr')
        result=compare(blob,ref)
        self.assertFalse(result['return_boundary']['verified_complete_jr_ra_return'])

    def test_failed_return_delay_slot_blocks_numeric_match(self):
        blob,ref=return_capture(bad_delay_slot=True)
        result=compare(blob,ref)
        self.assertFalse(result['guest_completed_at_expected_stop'])
        self.assertFalse(result['coefficient_comparison_performed'])

    def test_all_nine_sh_but_pending_load_at_return_is_not_strictly_verified(self):
        words=[op(9,0,8,4096)] + [op(41,5,8,i*2) for i in range(9)]
        words.extend([jr(),op(35,5,9,0)])
        blob=synthetic_exe(words)
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['gpr'][31]=BASE+len(words)*4
        ref['require_completed_jr_ra']=True
        result=compare(blob,ref)
        self.assertTrue(result['all_nine_final_sh_verified'])
        self.assertTrue(result['return_boundary']['jr_ra_delay_slot_executed_last'])
        self.assertFalse(result['return_boundary']['no_pending_delayed_load_at_stop'])
        self.assertFalse(result['coefficient_comparison_performed'])

    def test_stopping_before_return_opcode_cannot_claim_completed_return(self):
        words=[op(9,0,8,4096)] + [op(41,5,8,i*2) for i in range(9)]
        words.extend([jr(),0])
        blob=synthetic_exe(words)
        ref=fixture(blob,source='external_ps1_capture_claim')
        ref['stop_pc']=BASE+4*10  # immediately before JR $ra
        ref['gpr'][31]=BASE+4*len(words)
        ref['require_completed_jr_ra']=True
        result=compare(blob,ref)
        self.assertTrue(result['guest_completed_at_expected_stop'])
        self.assertTrue(result['all_nine_final_sh_verified'])
        self.assertFalse(result['return_boundary']['verified_complete_jr_ra_return'])
        self.assertFalse(result['coefficient_comparison_performed'])

    def test_malformed_return_option_is_rejected(self):
        blob,ref=return_capture()
        for value in (1,'true',None,[],{}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                ref['require_completed_jr_ra']=value
                compare(blob,ref)

    def test_capture_pack_forwards_explicit_return_requirement(self):
        exe,before,after,before_ram,after_ram=dumps()
        p=pack(exe,before,after,before_ram,after_ram,ram_base=BASE,
               require_completed_jr_ra=True)
        self.assertTrue(p['require_completed_jr_ra'])
        result=compare(exe,p)
        self.assertFalse(result['coefficient_comparison_performed'])

    def test_capture_pack_rejects_malformed_return_requirement(self):
        exe,before,after,before_ram,after_ram=dumps()
        with self.assertRaises(ValueError):
            pack(exe,before,after,before_ram,after_ram,ram_base=BASE,
                 require_completed_jr_ra='yes')

    def test_packaging_cli_propagates_require_jr_return_flag(self):
        exe,before,after,before_ram,after_ram=dumps()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            paths=[root/n for n in ('exe','before.json','after.json','before.bin','after.bin','capture.json')]
            paths[0].write_bytes(exe)
            paths[1].write_text(json.dumps(before))
            paths[2].write_text(json.dumps(after))
            paths[3].write_bytes(before_ram)
            paths[4].write_bytes(after_ram)
            import contextlib
            from io import StringIO
            out=StringIO()
            with contextlib.redirect_stdout(out):
                status=main(['--exe',str(paths[0]),'--before-registers',str(paths[1]),
                             '--after-registers',str(paths[2]),'--before-ram',str(paths[3]),
                             '--after-ram',str(paths[4]),'--ram-base',hex(BASE),
                             '--output',str(paths[5]),'--require-jr-return'])
            self.assertEqual(status,0)
            self.assertTrue(json.loads(paths[5].read_text())['require_completed_jr_ra'])
            self.assertNotIn('4096',out.getvalue())

    def test_return_report_does_not_publish_guest_values(self):
        blob,ref=return_capture()
        result=compare(blob,ref)
        returned=str(result['return_boundary'])
        self.assertNotIn(hex(BASE),returned)
        self.assertNotIn('4096',returned)
        self.assertFalse(result['return_boundary']['private_values_emitted'])


if __name__=='__main__': unittest.main()
