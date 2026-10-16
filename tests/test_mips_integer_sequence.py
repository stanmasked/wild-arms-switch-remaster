import unittest
from tools.mips_integer_sequence import execute

def imm(op, rs, rt, value):
    return (op << 26) | (rs << 21) | (rt << 16) | (value & 65535)

def reg(fn, rs=0, rt=0, rd=0, shift=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (shift << 6) | fn

class IntegerSequenceTests(unittest.TestCase):
    def test_multiply_shift_chain(self):
        result = execute([imm(9, 0, 8, -3), imm(9, 0, 9, 7),
                          reg(24, 8, 9), reg(18, rd=10),
                          reg(3, rt=10, rd=11, shift=2)])
        self.assertTrue(result['completed'])
        self.assertEqual(result['lo'], 0xffffffeb)
        self.assertEqual(result['gpr'][11], 0xfffffffa)
        self.assertEqual(result['executed'], 5)
    def test_rejects_memory_and_preserves_prefix(self):
        result = execute([imm(9, 0, 8, 1), imm(35, 8, 9, 0),
                          imm(9, 0, 10, 3)])
        self.assertEqual((result['reason'], result['index'], result['executed']),
                         ('ValueError', 1, 1))
        self.assertEqual((result['gpr'][8], result['gpr'][10]), (1, 0))
    def test_signed_overflow_stops_execution(self):
        initial = [0]*32
        initial[8] = 0x7fffffff
        result = execute([imm(8, 8, 9, 1)], initial)
        self.assertEqual(result['reason'], 'OverflowError')
        self.assertEqual(result['executed'], 0)
    def test_step_limit(self):
        result = execute([0, 0, 0], max_steps=2)
        self.assertEqual((result['reason'],result['executed'],result['index']),
                         ('step_limit',2,2))
    def test_zero_register_stays_zero(self):
        initial=[99]+[0]*31
        result=execute([imm(15,0,0,0xffff)],initial)
        self.assertTrue(result['completed'])
        self.assertEqual(result['gpr'][0],0)
    def test_empty_sequence(self):
        result=execute([])
        self.assertTrue(result['completed'])
        self.assertEqual(result['executed'],0)

if __name__=='__main__':
    unittest.main()
