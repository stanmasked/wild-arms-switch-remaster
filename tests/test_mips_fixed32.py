import unittest
from tools.mips_fixed32 import u32,s32,sign_extend16,split64,mult,sll,srl,sra,add32,sub32,addiu,slt

class MIPSFixed32Tests(unittest.TestCase):
    def test_signed_and_unsigned_products(self):
        self.assertEqual(mult(-1,2), (0xffffffff,0xfffffffe))
        self.assertEqual(mult(-1,2,signed=False), (1,0xfffffffe))
        self.assertEqual(mult(0x80000000,2), (0xffffffff,0))
        self.assertEqual(mult(0xffffffff,0xffffffff), (0,1))
    def test_sra_vs_srl(self):
        self.assertEqual(sra(0x80000000,1),0xc0000000)
        self.assertEqual(srl(0x80000000,1),0x40000000)
        self.assertEqual(sll(0xffffffff,1),0xfffffffe)
        self.assertEqual(sra(0xffffffff,31),0xffffffff)
    def test_32bit_wrapping_and_overflow(self):
        self.assertEqual(add32(0x7fffffff,1),(0x80000000,True))
        with self.assertRaises(OverflowError):
            add32(0x7fffffff,1,True)
        self.assertEqual(sub32(0x80000000,1),(0x7fffffff,True))
        self.assertEqual(add32(-1,1),(0,False))
    def test_immediate_signed(self):
        self.assertEqual(sign_extend16(0xffff),-1)
        self.assertEqual(addiu(0,0xffff),0xffffffff)
        self.assertEqual(addiu(0xffffffff,1),0)
    def test_unsigned_comparison(self):
        self.assertEqual(slt(-1,0),1)
        self.assertEqual(slt(-1,0,unsigned=True),0)
    def test_split64(self):
        self.assertEqual(split64(-1),(0xffffffff,0xffffffff))

if __name__=='__main__':
    unittest.main()
