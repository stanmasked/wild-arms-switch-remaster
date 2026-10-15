import unittest
from tools.verify_indexed_init_call import (verify_words, compute_stride, STRIDE_OPS, GLOBAL_OPS)

def fixture():
    w = [0]*47
    w[3:7] = STRIDE_OPS[:4]
    w[10] = STRIDE_OPS[4]
    w[8], w[9] = GLOBAL_OPS
    w[16:20] = [0x26040004, 0xA2020000, 0x0C01B39C, 0xA2060001]
    for i,v in {25:0xA6020052,26:0xA6120002,
                27:0xA6030050,39:0xAE030054}.items():
        w[i]=v
    return w

class InitCallerTests(unittest.TestCase):
    def test_stride(self):
        self.assertEqual([compute_stride(i) for i in (0,1,2,9)],
                         [0,88,176,792])
    def test_signature(self):
        self.assertEqual(verify_words(fixture())["record_stride_bytes"],88)
    def test_argument_offset(self):
        self.assertEqual(verify_words(fixture())["initializer_argument_offset"],4)
    def test_jal_delay_slot(self):
        self.assertEqual(fixture()[19],0xA2060001)
    def test_reject_other_callee(self):
        w=fixture();w[18]=0x0C000000
        with self.assertRaises(ValueError):verify_words(w)
    def test_reject_wrong_stride(self):
        w=fixture();w[6]=0
        with self.assertRaises(ValueError):verify_words(w)
    def test_reject_short(self):
        with self.assertRaises(ValueError):verify_words([0]*5)

if __name__ == "__main__":
    unittest.main()
