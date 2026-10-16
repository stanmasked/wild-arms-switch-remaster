import unittest
from tools.mips_trig_memory import (decode_entry,index_angle,entry_address,
    table_memory,read_entry,synthetic_cardinal_table)
from tools.mips_memory_sequence import execute

def i(op,rs,rt,imm):
    return op<<26|rs<<21|rt<<16|(imm&65535)
def r(fn,rs=0,rt=0,rd=0,sa=0):
    return rs<<21|rt<<16|rd<<11|sa<<6|fn

class TrigMemoryTests(unittest.TestCase):
    def test_cardinal_signs(self):
        mem=table_memory(0x100000,synthetic_cardinal_table())
        self.assertEqual(read_entry(mem,0),(0,4096))
        self.assertEqual(read_entry(mem,1024),(4096,0))
        self.assertEqual(read_entry(mem,2048),(0,-4096))
        self.assertEqual(read_entry(mem,3072),(-4096,0))
    def test_angle_wrap_and_address(self):
        self.assertEqual(index_angle(-1),4095)
        self.assertEqual(entry_address(0x100000,4096),0x100000)
        self.assertEqual(entry_address(0x100000,-1),0x103ffc)
    def test_reject_invalid_buffer(self):
        with self.assertRaises(ValueError): table_memory(0x100000,b'')
    def test_reject_unaligned_base(self):
        with self.assertRaises(ValueError):table_memory(0x100001,synthetic_cardinal_table())
    def test_signed_decoding(self):
        self.assertEqual(decode_entry(0xf0001000),(4096,-4096))
    def test_lw_mult_shift_chain(self):
        base=0x100000
        mem=table_memory(base,synthetic_cardinal_table())
        regs=[0]*32
        regs[8]=entry_address(base,1024)
        regs[9]=2
        # LW is followed by NOP to respect R3000A load delay.
        words=[i(35,8,10,0),0,r(24,10,9),r(18,rd=11),r(3,rt=11,rd=12,sa=1)]
        result=execute(words,mem,regs)
        self.assertTrue(result['completed'])
        self.assertEqual(result['gpr'][10],4096)
        self.assertEqual(result['gpr'][11],8192)
        self.assertEqual(result['gpr'][12],4096)

if __name__=='__main__':
    unittest.main()
