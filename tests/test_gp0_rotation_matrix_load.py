import struct
import unittest
from tools.audit_gp0_rotation_matrix_load import (
    audit,decode_ctc2,decode_lw,decode_stack_a0,jal_target)

BASE=0x80010000
CALL=BASE+8
LOADER=BASE+64
FOLLOW=BASE+160

def jal(target):return 3<<26|((target>>2)&0x3ffffff)
def addiu_a0_sp(off):return 9<<26|29<<21|4<<16|(off&65535)
def lw(rt,off,base=4):return 35<<26|base<<21|rt<<16|(off&65535)
def ctc2(rt,rd):return 18<<26|6<<21|rt<<16|rd<<11

def fixture():
    words=[0]*48
    words[2]=jal(LOADER)
    words[3]=addiu_a0_sp(16)
    for i in range(5):
        words[16+i]=lw(8+i,i*4)
        words[21+i]=ctc2(8+i,i)
    words[40]=jal(0x800B68E8)
    return words

def run(words):
    return audit(struct.pack('<%dI'%len(words),*words),BASE,CALL,LOADER,FOLLOW)

class RotationLoaderTests(unittest.TestCase):
    def test_lw_decoder(self):self.assertEqual(decode_lw(lw(8,0)),(8,4,0))
    def test_ctc2_decoder(self):self.assertEqual(decode_ctc2(ctc2(12,4)),(12,4))
    def test_signed_stack_arg(self):self.assertEqual(decode_stack_a0(addiu_a0_sp(-16)),-16)
    def test_jal_target(self):self.assertEqual(jal_target(jal(LOADER),CALL),LOADER)
    def test_five_word_loader(self):
        r=run(fixture())
        self.assertTrue(r['five_rotation_control_words'])
        self.assertTrue(r['loader_called'])
        self.assertEqual(r['delay_slot_a0_stack_offset'],16)
        self.assertTrue(r['downstream_mvmva_helper_call'])
    def test_wrong_control_register(self):
        w=fixture();w[24]=ctc2(11,8)
        self.assertFalse(run(w)['five_rotation_control_words'])
    def test_wrong_source_offset(self):
        w=fixture();w[18]=lw(10,12)
        self.assertFalse(run(w)['five_rotation_control_words'])
    def test_wrong_pointer_base(self):
        w=fixture();w[17]=lw(9,4,5)
        self.assertFalse(run(w)['five_rotation_control_words'])
    def test_wrong_call_target(self):
        w=fixture();w[2]=jal(LOADER+4)
        self.assertFalse(run(w)['loader_called'])
    def test_missing_delay_arg(self):
        w=fixture();w[3]=0
        self.assertIsNone(run(w)['delay_slot_a0_stack_offset'])
    def test_empty_image_no_false_matches(self):
        r=audit(b'',BASE,CALL,LOADER,FOLLOW)
        self.assertFalse(r['loader_called'])
        self.assertFalse(r['five_rotation_control_words'])
        self.assertFalse(r['runtime_matrix_coefficients_recovered'])

if __name__=='__main__':unittest.main()
