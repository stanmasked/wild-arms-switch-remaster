import unittest
from tools.mips_integer_step import step

def r(fn,rs=0,rt=0,rd=0,sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn
def i(op,rs,rt,imm):
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&65535)
def regs(**values):
    data=[0]*32
    for key,value in values.items():data[int(key[1:])]=value
    return data

class StepTests(unittest.TestCase):
    def test_mult_and_mflo(self):
        a,h,l=step(r(24,8,9),regs(r8=0xffffffff,r9=2))
        self.assertEqual((h,l),(0xffffffff,0xfffffffe))
        b,h,l=step(r(18,rd=10),a,h,l)
        self.assertEqual(b[10],0xfffffffe)
    def test_arithmetic_shift(self):
        a,_,_=step(r(3,rt=8,rd=10,sa=12),regs(r8=0x80000000))
        self.assertEqual(a[10],0xfff80000)
    def test_addiu_sign_extended(self):
        a,_,_=step(i(9,0,8,-1),[0]*32)
        self.assertEqual(a[8],0xffffffff)
    def test_signed_add_overflow(self):
        with self.assertRaises(OverflowError):
            step(r(32,8,9,10),regs(r8=0x7fffffff,r9=1))
    def test_zero_register_immutable(self):
        a,_,_=step(i(15,0,0,0xffff),[9]+[0]*31)
        self.assertEqual(a[0],0)
    def test_unsupported_memory_rejected(self):
        with self.assertRaises(ValueError):
            step(i(35,8,9,0),[0]*32)
    def test_sltu(self):
        a,_,_=step(r(43,8,9,10),regs(r8=0xffffffff,r9=0))
        self.assertEqual(a[10],0)

if __name__=='__main__':
    unittest.main()
