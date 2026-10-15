import struct
import unittest
from tools.audit_gp0_rotation_matrix_builder import (
    EXPECTED_HALFWORDED_OFFSETS, analyze, global_lw_address, jal_target, sw_halfword)

BASE=0x80010000
START=BASE+0x80
END=START+0x60
CALL=BASE+0x40

def sh(rt,base,offset): return 0x29<<26|base<<21|rt<<16|(offset&65535)
def addiu(rt,base,off): return 9<<26|base<<21|rt<<16|(off&65535)
def jal(addr): return 3<<26|((addr>>2)&0x3ffffff)
def words(*args): return struct.pack(f'<{len(args)}I',*args)
def fixture():
    blob=[0]*64
    blob[(CALL-BASE)//4]=jal(START)
    blob[(CALL-BASE)//4-4]=addiu(5,29,16)
    for index, offset in enumerate(EXPECTED_HALFWORDED_OFFSETS):
        blob[(START-BASE)//4+index]=sh(14,5,offset)
    return blob

def check(blob):
    return analyze(words(*blob),BASE,START,END,CALL)

class MatrixBuilderTests(unittest.TestCase):
    def test_expected_nine_offsets(self):
        self.assertEqual(EXPECTED_HALFWORDED_OFFSETS,tuple(range(0,18,2)))
    def test_halfword_decode(self):
        self.assertEqual(sw_halfword(sh(14,5,-4)),{'base':5,'value_register':14,'offset':-4})
    def test_reject_other_store(self):
        self.assertIsNone(sw_halfword((43<<26)|(5<<21)|(14<<16)|8))
    def test_complete_matrix(self):
        report=check(fixture())
        self.assertTrue(report['complete_matrix_slots'])
        self.assertTrue(report['builder_called'])
        self.assertTrue(report['a1_is_stack_plus_16'])
        self.assertFalse(report['runtime_coefficients_recovered'])
    def test_missing_slot(self):
        f=fixture();f[(START-BASE)//4+6]=0
        self.assertFalse(check(f)['complete_matrix_slots'])
    def test_other_pointer_base(self):
        f=fixture();f[(START-BASE)//4+6]=sh(14,4,12)
        self.assertFalse(check(f)['complete_matrix_slots'])
    def test_duplicate_slot_still_nine_unique(self):
        f=fixture();f[(START-BASE)//4+10]=sh(14,5,16)
        self.assertTrue(check(f)['complete_matrix_slots'])
        self.assertEqual(len(check(f)['matrix_halfword_writes']),10)
    def test_signed_global_address(self):
        lui=15<<26|25<<16|0x800d
        lw=35<<26|25<<21|25<<16|0xbe44
        self.assertEqual(global_lw_address(lui,lw),0x800cbe44)
    def test_global_register_must_match(self):
        self.assertIsNone(global_lw_address(15<<26|25<<16|0x800d,
            35<<26|24<<21|25<<16|0xbe44))
    def test_wrong_jal_target(self):
        f=fixture();f[(CALL-BASE)//4]=jal(START+4)
        self.assertFalse(check(f)['builder_called'])
    def test_wrong_stack_pointer(self):
        f=fixture();f[(CALL-BASE)//4-4]=addiu(5,29,20)
        self.assertFalse(check(f)['a1_is_stack_plus_16'])
    def test_invalid_range(self):
        self.assertFalse(analyze(b'',BASE,START,END,CALL)['valid_range'])

if __name__=='__main__':unittest.main()
