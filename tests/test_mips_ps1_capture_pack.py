"""Synthetic debugger pre/post captures, not real PlayStation game data."""
import copy
import hashlib
import struct
import unittest

from tools.mips_ps1_capture_pack import (pack, summarize_capture,
                                         REGISTERS_SCHEMA)
from tools.mips_ps1_matrix_reference import compare, SCHEMA
from tests.test_mips_ps1_matrix_reference import synthetic_program

BASE = 0x80010000
MATRIX = BASE + 0x100


def dumps(*, coefficient=4096, size=512, ram_base=BASE, program=None):
    exe = synthetic_program(coefficient) if program is None else program
    before = bytearray(size)
    after = bytearray(size)
    image = exe[2048:]
    if (BASE >= ram_base and BASE - ram_base + len(image) <= size):
        before[BASE-ram_base:BASE-ram_base+len(image)] = image
        after[BASE-ram_base:BASE-ram_base+len(image)] = image
    offset = MATRIX-ram_base
    if 0 <= offset and offset + 18 <= size:
        struct.pack_into('<9h', after, offset, *([coefficient]*9))
    regs = [0]*32
    regs[5] = MATRIX
    before_regs = {'schema':REGISTERS_SCHEMA,'pc':BASE,'gpr':regs,
                   'hi':0,'lo':0}
    after_regs = {'schema':REGISTERS_SCHEMA,'pc':BASE+len(image)}
    return exe, before_regs, after_regs, bytes(before), bytes(after)


class CapturePackTests(unittest.TestCase):
    def test_two_phase_debugger_exports_create_exact_stage211_reference(self):
        exe,r0,r1,before,after = dumps()
        result = pack(exe,r0,r1,before,after,ram_base=BASE,source='synthetic')
        self.assertEqual(result['schema'],SCHEMA)
        self.assertEqual(result['expected_matrix_s16'],[4096]*9)
        self.assertEqual(result['exe_sha256'],hashlib.sha256(exe).hexdigest())
        self.assertTrue(compare(exe,result)['matches_supplied_nine_coefficients'])
        self.assertEqual(result['memory_segments'][0]['data_hex'],before.hex())

    def test_post_capture_is_not_copied_in_bulk_into_before_memory(self):
        exe,r0,r1,before,after = dumps()
        result = pack(exe,r0,r1,before,after,ram_base=BASE)
        self.assertEqual(result['memory_segments'][0]['data_hex'],before.hex())
        self.assertNotEqual(result['memory_segments'][0]['data_hex'],after.hex())
        self.assertEqual(result['source'],'external_ps1_capture_claim')

    def test_external_claim_is_not_verified_hardware(self):
        exe,r0,r1,before,after = dumps()
        result = pack(exe,r0,r1,before,after,ram_base=BASE)
        comparison = compare(exe,result)
        self.assertTrue(comparison['supplied_reference_is_claimed_external_capture'])
        self.assertFalse(comparison['external_ps1_capture_authenticity_independently_verified'])

    def test_auto_matrix_pointer_from_before_a1(self):
        exe,r0,r1,before,after = dumps()
        result = pack(exe,r0,r1,before,after,ram_base=BASE)
        self.assertEqual(result['matrix_address'],r0['gpr'][5])

    def test_explicit_matrix_address_overrides_a1(self):
        exe,r0,r1,before,after = dumps()
        r0['gpr'][5] = MATRIX + 18
        result=pack(exe,r0,r1,before,after,ram_base=BASE,matrix_address=MATRIX)
        self.assertEqual(result['matrix_address'],MATRIX)
        self.assertFalse(compare(exe,result)['matches_supplied_nine_coefficients'])

    def test_negative_signed_coefficients_in_after_ram(self):
        exe,r0,r1,before,after=dumps(coefficient=-1)
        result=pack(exe,r0,r1,before,after,ram_base=BASE)
        self.assertEqual(result['expected_matrix_s16'],[-1]*9)
        self.assertTrue(compare(exe,result)['matches_supplied_nine_coefficients'])

    def test_end_pc_must_differ_from_start(self):
        exe,r0,r1,before,after=dumps()
        r1['pc']=r0['pc']
        with self.assertRaises(ValueError):pack(exe,r0,r1,before,after,ram_base=BASE)

    def test_before_entry_must_belong_to_exe(self):
        exe,r0,r1,before,after=dumps()
        r0['pc']=BASE+0x1000
        with self.assertRaises(ValueError):pack(exe,r0,r1,before,after,ram_base=BASE)

    def test_unaligned_after_pc_rejected(self):
        exe,r0,r1,before,after=dumps()
        r1['pc']=BASE+1
        with self.assertRaises(ValueError):pack(exe,r0,r1,before,after,ram_base=BASE)

    def test_no_missing_before_registers_can_be_guessed(self):
        exe,r0,r1,before,after=dumps()
        for mutation in ('missing','wrong_count','nonzero_r0','missing_hi'):
            q=copy.deepcopy(r0)
            if mutation=='missing':q.pop('gpr')
            elif mutation=='wrong_count':q['gpr']=q['gpr'][:-1]
            elif mutation=='nonzero_r0':q['gpr'][0]=4
            else:q.pop('hi')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                pack(exe,q,r1,before,after,ram_base=BASE)

    def test_ram_lengths_must_match(self):
        exe,r0,r1,before,after=dumps()
        with self.assertRaises(ValueError):
            pack(exe,r0,r1,before,after[:-1],ram_base=BASE)

    def test_matrix_must_fit_both_dumps(self):
        exe,r0,r1,before,after=dumps()
        for matrix in (BASE-2,BASE+511,BASE+512,BASE+1):
            with self.subTest(matrix=matrix),self.assertRaises(ValueError):
                pack(exe,r0,r1,before,after,ram_base=BASE,matrix_address=matrix)

    def test_unrecognized_capture_source_fails_closed(self):
        exe,r0,r1,before,after=dumps()
        with self.assertRaises(ValueError):
            pack(exe,r0,r1,before,after,ram_base=BASE,source='ps1_authenticated')

    def test_bad_input_types_and_budget_fail_closed(self):
        exe,r0,r1,before,after=dumps()
        for kwargs in ({'ram_base':'0xZZ'}, {'max_steps':0},
                       {'max_steps':True}, {'max_steps':100001}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                pack(exe,r0,r1,before,after,**({'ram_base':BASE}|kwargs))

    def test_2mib_full_ram_dump_uses_virtual_kseg0_base(self):
        exe,r0,r1,before,after=dumps(size=2*1024*1024,ram_base=0x80000000)
        result=pack(exe,r0,r1,before,after,ram_base='0x80000000',source='synthetic')
        self.assertTrue(compare(exe,result)['matches_supplied_nine_coefficients'])
        self.assertEqual(len(result['memory_segments'][0]['data_hex']),4*1024*1024)

    def test_different_after_coefficients_can_be_detected_later(self):
        exe,r0,r1,before,after=dumps()
        mutated=bytearray(after)
        struct.pack_into('<h',mutated,MATRIX-BASE+4,55)
        result=pack(exe,r0,r1,before,bytes(mutated),ram_base=BASE)
        compared=compare(exe,result)
        self.assertFalse(compared['matches_supplied_nine_coefficients'])
        self.assertEqual(compared['mismatch_slot_indices'],[2])

    def test_incomplete_original_program_cannot_claim_nine_matching_sh(self):
        exe=synthetic_program(slots=7)
        _,r0,r1,before,after=dumps(program=exe)
        result=pack(exe,r0,r1,before,after,ram_base=BASE)
        compared=compare(exe,result)
        self.assertFalse(compared['coefficient_comparison_performed'])
        self.assertEqual(compared['final_halfword_slots_written_by_sh'],7)

    def test_safe_summary_does_not_expose_memory_registers_or_coefficients(self):
        exe,r0,r1,before,after=dumps()
        result=pack(exe,r0,r1,before,after,ram_base=BASE)
        summary=summarize_capture(result)
        self.assertEqual(summary['after_matrix_coefficient_count'],9)
        self.assertFalse(summary['ps1_capture_authenticity_independently_verified'])
        self.assertFalse(summary['same_game_session_verified'])
        self.assertFalse(summary['private_values_emitted'])
        self.assertNotIn('4096',str(summary))
        self.assertNotIn('0x800',str(summary))


if __name__=='__main__':unittest.main()
