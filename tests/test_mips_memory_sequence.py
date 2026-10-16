import unittest
from tools.mips_memory_sequence import Memory,execute

def ins(op,rs,rt,imm):
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)

class MemorySequenceTests(unittest.TestCase):
    def test_load_delay(self):
        m=Memory(0x1000,bytes.fromhex('04030000')+bytes(12))
        regs=[0]*32; regs[8]=0x1000
        r=execute([ins(35,8,9,0),ins(9,9,10,1),ins(9,9,11,1)],m,regs)
        self.assertTrue(r['completed'])
        self.assertEqual(r['gpr'][10],1)
        self.assertEqual(r['gpr'][11],773)
    def test_load_followed_by_same_register_write(self):
        m=Memory(0x1000,(123).to_bytes(4,'little'))
        regs=[0]*32;regs[8]=0x1000
        r=execute([ins(35,8,9,0),ins(9,0,9,7)],m,regs)
        self.assertEqual(r['gpr'][9],7)
    def test_store_little_endian(self):
        m=Memory(0x1000,bytes(8))
        regs=[0]*32;regs[8]=0x1000;regs[9]=0x12345678
        r=execute([ins(41,8,9,2)],m,regs)
        self.assertTrue(r['completed'])
        self.assertEqual(m.data[2:4],bytes.fromhex('7856'))
    def test_bounds_and_alignment(self):
        m=Memory(0x1000,bytes(4));regs=[0]*32;regs[8]=0x1000
        self.assertEqual(execute([ins(35,8,9,2)],m,regs)['reason'],'ValueError')
        self.assertEqual(execute([ins(35,8,9,4)],m,regs)['reason'],'ValueError')
    def test_signed_halfword(self):
        m=Memory(0x1000,bytes.fromhex('00f00000'))
        regs=[0]*32;regs[8]=0x1000
        r=execute([ins(33,8,9,0),0],m,regs)
        self.assertEqual(r['gpr'][9],0xfffff000)
    def test_final_load_pending(self):
        m=Memory(0x1000,(5).to_bytes(4,'little'))
        regs=[0]*32;regs[8]=0x1000
        r=execute([ins(35,8,9,0)],m,regs)
        self.assertEqual(r['gpr'][9],0)
        self.assertEqual(r['pending_load'],(9,5))

if __name__=='__main__':
    unittest.main()
