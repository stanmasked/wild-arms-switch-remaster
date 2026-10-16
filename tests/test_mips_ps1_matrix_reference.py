"""Independent mock external coefficient captures (no original game assets)."""
import copy
import hashlib
import struct
import unittest
from tools.mips_ps1_matrix_reference import compare, SCHEMA

BASE=0x80010000
MATRIX=0x80110000

def op(code,rs=0,rt=0,imm=0):
    return (code<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)

def synthetic_program(value=4096, slots=9, *, overwrite=False):
    words=[op(9,0,8,value)]
    words += [op(41,5,8,i*2) for i in range(slots)]
    if overwrite:
        words.append(op(43,5,0,0))
    payload=struct.pack('<%dI'%len(words),*words)
    header=bytearray(2048);header[:8]=b'PS-X EXE'
    struct.pack_into('<II',header,0x18,BASE,len(payload))
    return bytes(header)+payload

def fixture(blob, *, matrix=MATRIX, values=None, source='synthetic'):
    regs=[0]*32
    regs[5]=matrix
    return {'schema':SCHEMA,'source':source,'exe_sha256':hashlib.sha256(blob).hexdigest(),
            'entry_pc':f'0x{BASE:08x}', 'stop_pc':BASE+len(blob)-2048,
            'matrix_address':matrix,'gpr':regs,'hi':0,'lo':0,
            'expected_matrix_s16': ([4096]*9 if values is None else values),
            'memory_segments':[{'address':matrix,'data_hex':'00'*18}]}

class ReferenceComparisonTests(unittest.TestCase):
    def test_nine_exact_matches_synthetic_capture(self):
        blob=synthetic_program()
        result=compare(blob,fixture(blob))
        self.assertTrue(result['sha256_match'])
        self.assertTrue(result['guest_completed_at_expected_stop'])
        self.assertTrue(result['coefficient_comparison_performed'])
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertEqual(result['matching_coefficient_count'],9)
        self.assertEqual(result['mismatch_slot_indices'],[])
        self.assertFalse(result['original_playstation_hardware_equivalence_proven'])
        self.assertFalse(result['external_ps1_capture_authenticity_independently_verified'])

    def test_mismatch_only_exposes_slot_numbers(self):
        blob=synthetic_program()
        capture=fixture(blob,values=[4096]*8+[123])
        result=compare(blob,capture)
        self.assertEqual(result['matching_coefficient_count'],8)
        self.assertEqual(result['mismatch_slot_indices'],[8])
        self.assertFalse(result['matches_supplied_nine_coefficients'])
        self.assertNotIn('123',str(result))
        self.assertNotIn('4096',str(result))

    def test_signed_negative_sh_is_compared_as_signed(self):
        blob=synthetic_program(-1)
        ref=fixture(blob,values=[-1]*9)
        self.assertTrue(compare(blob,ref)['matches_supplied_nine_coefficients'])

    def test_missing_sh_can_never_match_even_with_preloaded_expected_memory(self):
        blob=synthetic_program(slots=8)
        f=fixture(blob)
        f['memory_segments'][0]['data_hex']=struct.pack('<9h',*[4096]*9).hex()
        report=compare(blob,f)
        self.assertEqual(report['final_halfword_slots_written_by_sh'],8)
        self.assertFalse(report['coefficient_comparison_performed'])
        self.assertIsNone(report['matching_coefficient_count'])

    def test_overlapping_sw_revokes_final_sh(self):
        blob=synthetic_program(overwrite=True)
        rep=compare(blob,fixture(blob))
        self.assertEqual(rep['final_halfword_slots_written_by_sh'],7)
        self.assertFalse(rep['coefficient_comparison_performed'])

    def test_step_limit_disables_comparison(self):
        blob=synthetic_program()
        ref=fixture(blob);ref['max_steps']=3
        rep=compare(blob,ref)
        self.assertEqual(rep['guest_stop_reason'],'step_limit')
        self.assertFalse(rep['coefficient_comparison_performed'])

    def test_wrong_sha_refuses_rather_than_comparing(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['exe_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            compare(blob,ref)

    def test_capture_claim_never_certifies_hardware(self):
        blob=synthetic_program();ref=fixture(blob,source='external_ps1_capture_claim')
        rep=compare(blob,ref)
        self.assertTrue(rep['supplied_reference_is_claimed_external_capture'])
        self.assertFalse(rep['external_ps1_capture_authenticity_independently_verified'])
        self.assertFalse(rep['original_playstation_hardware_equivalence_proven'])

    def test_mismatched_exe_bytes_even_if_same_size_are_rejected(self):
        a,b=synthetic_program(),synthetic_program(1)
        with self.assertRaises(ValueError):compare(b,fixture(a))

    def test_strict_nine_coefficients_and_sign_range(self):
        blob=synthetic_program()
        for values in ([],[0]*8,[0]*10,[32768]*9,[-32769]*9,[True]*9):
            with self.subTest(values=values),self.assertRaises(ValueError):
                compare(blob,fixture(blob,values=values))

    def test_all_32_gprs_required_and_r0_must_be_zero(self):
        blob=synthetic_program()
        ref=fixture(blob);ref['gpr']=[0]*31
        with self.assertRaises(ValueError):compare(blob,ref)
        ref=fixture(blob);ref['gpr']=[0]*32;ref['gpr'][0]=1
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_extra_mapped_ram_data_required(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['memory_segments']=[]
        with self.assertRaisesRegex(ValueError,'snapshot must map'):
            compare(blob,ref)

    def test_partial_matrix_memory_fails_before_execution(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['memory_segments'][0]['data_hex']='00'*16
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_segment_overlap_fails(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['memory_segments'].append({'address':MATRIX+6,'data_hex':'00'*4})
        with self.assertRaisesRegex(ValueError,'overlapping'):
            compare(blob,ref)

    def test_patch_over_executable_image_is_marked_and_affects_execution(self):
        blob=synthetic_program();ref=fixture(blob)
        # Change first instruction from ADDIU t0,4096 to ADDIU t0,42.
        ref['memory_segments'].append({'address':BASE,'data_hex':struct.pack('<I',op(9,0,8,42)).hex()})
        ref['expected_matrix_s16']=[42]*9
        result=compare(blob,ref)
        self.assertTrue(result['executable_memory_overlaid'])
        self.assertTrue(result['matches_supplied_nine_coefficients'])

    def test_patch_straddling_code_image_splits_into_mapped_ram(self):
        blob=synthetic_program();ref=fixture(blob)
        payload=blob[2048:]
        # Segment reaches from before the EXE into its first instruction,
        # crossing an EXE boundary without changing that opcode.
        ref['memory_segments'].append({
            'address':BASE-4,
            'data_hex':('abcd1234' + payload[:4].hex())})
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertTrue(result['executable_memory_overlaid'])

    def test_whole_ram_segment_containing_image_can_be_used(self):
        blob=synthetic_program();ref=fixture(blob)
        payload=blob[2048:]
        ram=bytes(8)+payload+bytes(8)
        # The reference matrix is at an independent address.
        ref['memory_segments'].append({'address':BASE-8,'data_hex':ram.hex()})
        result=compare(blob,ref)
        self.assertTrue(result['matches_supplied_nine_coefficients'])

    def test_bad_hex_and_memory_limits_rejected(self):
        blob=synthetic_program()
        for data in ('zz','0', '', 'xyyz'):
            ref=fixture(blob);ref['memory_segments'][0]['data_hex']=data
            with self.subTest(data=data),self.assertRaises(ValueError):compare(blob,ref)
        ref=fixture(blob);ref['memory_segments']=[{'address':MATRIX,'data_hex':'00'*(4*1024*1024+1)}]
        with self.assertRaises(ValueError):compare(blob,ref)

    def test_invalid_u32_addresses_and_budgets(self):
        blob=synthetic_program()
        for key,value in (('entry_pc','-1'),('stop_pc',-1),('matrix_address',MATRIX+1),
                          ('max_steps',0),('max_steps',100001),('entry_pc',True)):
            ref=fixture(blob);ref[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                compare(blob,ref)

    def test_stopping_before_first_instruction_does_not_compare(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['stop_pc']=BASE
        result=compare(blob,ref)
        self.assertTrue(result['guest_completed_at_expected_stop'])
        self.assertFalse(result['coefficient_comparison_performed'])

    def test_fail_closed_for_unsupported_guest_instruction(self):
        blob=synthetic_program();ref=fixture(blob)
        ref['memory_segments'].append({'address':BASE,'data_hex':struct.pack('<I',18<<26).hex()})
        result=compare(blob,ref)
        self.assertEqual(result['guest_stop_reason'],'ValueError')
        self.assertFalse(result['coefficient_comparison_performed'])
        self.assertFalse(result['private_values_emitted'])

    def test_reject_unrecognized_capture_origin_or_schema(self):
        blob=synthetic_program()
        for key,value in (('source','verified_playstation'),('schema','anything_else')):
            ref=fixture(blob);ref[key]=value
            with self.assertRaises(ValueError):compare(blob,ref)

class OracleBackedMatrixComparisonTests(unittest.TestCase):
    def test_nine_signed_mult_sra_sh_coefficients_match_independent_oracle(self):
        from tools.mips_q12_arithmetic_reference import sh_q12_product, signed16
        left = [0, 0x1000, 0xf000, 0xffff, 0x8000, 0x7fff, 17, 37, 4095]
        right = [0x1000,0x1000,0x1000,0x0001,0x8000,0x1000,0xffff,0x8000,0x8001]
        words=[]
        for i in range(9):
            words.extend([op(33,16,8,2*i),op(33,17,9,2*i),0,
                          (8<<21)|(9<<16)|24,
                          (10<<11)|18,
                          (10<<16)|(10<<11)|(12<<6)|3,
                          op(41,5,10,2*i)])
        payload=struct.pack('<%dI'%len(words),*words)
        header=bytearray(2048);header[:8]=b'PS-X EXE'
        struct.pack_into('<II',header,0x18,BASE,len(payload))
        blob=bytes(header)+payload
        ref=fixture(blob,values=[signed16(sh_q12_product(a,b))
                                 for a,b in zip(left,right)])
        ref['gpr'][16]=0x80100000
        ref['gpr'][17]=0x80100100
        ref['memory_segments'].extend([
            {'address':0x80100000,'data_hex':struct.pack('<9H',*left).hex()},
            {'address':0x80100100,'data_hex':struct.pack('<9H',*right).hex()},
        ])
        self.assertTrue(compare(blob,ref)['matches_supplied_nine_coefficients'])

if __name__=='__main__':unittest.main()
