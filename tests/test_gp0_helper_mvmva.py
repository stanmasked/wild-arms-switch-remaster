import struct
import unittest
from tools.audit_gp0_helper_mvmva import instruction, scan

BASE = 0x80010000

def lw(rt, rs, imm): return (35 << 26) | (rs << 21) | (rt << 16) | (imm & 65535)
def mtc2(rt, rd): return (18 << 26) | (4 << 21) | (rt << 16) | (rd << 11)
def swc2(rt, rs, imm): return (58 << 26) | (rs << 21) | (rt << 16) | (imm & 65535)
def image(words): return struct.pack('<%dI' % len(words), *words)
def sample():
    return [lw(8,4,0),lw(9,4,4),mtc2(8,0),mtc2(9,1),0,
            0x4a486012,swc2(9,5,0),swc2(10,5,4),swc2(11,5,8),0]

class HelperMvmvaTests(unittest.TestCase):
    def test_input_lw(self): self.assertEqual(instruction(lw(8,4,0)),('LW',8,4,0))
    def test_input_mtc2(self): self.assertEqual(instruction(mtc2(9,1)),('MTC2',9,1))
    def test_command(self): self.assertEqual(instruction(0x4a486012),('GTE',0x12))
    def test_signed_swc2(self): self.assertEqual(instruction(swc2(11,5,-4)),('SWC2',11,5,-4))
    def test_full_original_pattern(self):
        result=scan(image(sample()),BASE,BASE)
        self.assertTrue(result['matched'])
        self.assertEqual(result['a1_word_offsets'],[0,4,8])
        self.assertFalse(result['gp0_opcode_or_uv_recovered'])
    def test_wrong_destination_pointer(self):
        words=sample();words[7]=swc2(10,6,4)
        self.assertFalse(scan(image(words),BASE,BASE)['matched'])
    def test_wrong_gte_register(self):
        words=sample();words[6]=swc2(12,5,0)
        self.assertFalse(scan(image(words),BASE,BASE)['matched'])
    def test_wrong_command(self):
        words=sample();words[5]=0x4a486006
        self.assertFalse(scan(image(words),BASE,BASE)['matched'])
    def test_wrong_input(self):
        words=sample();words[1]=lw(9,4,8)
        self.assertFalse(scan(image(words),BASE,BASE)['matched'])
    def test_short_or_misaligned(self):
        self.assertFalse(scan(b'',BASE,BASE)['matched'])
        self.assertFalse(scan(image(sample()),BASE,BASE+2)['matched'])

if __name__=='__main__': unittest.main()
