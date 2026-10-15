import unittest
from tools.verify_record_clear import EXPECTED, verify

class ClearLoopTests(unittest.TestCase):
    def test_exact_pattern(self):
        self.assertEqual(verify(EXPECTED)['slot_count'],16)
    def test_stride_and_last_offset(self):
        r=verify(EXPECTED)
        self.assertEqual(r['stride_bytes'],88)
        self.assertEqual(r['last_cleared_offset'],1320)
    def test_branch_delay_slot(self):
        self.assertEqual(EXPECTED[5],0x0441fffd)
        self.assertEqual(EXPECTED[6],0x24630058)
    def test_modified_counter_rejected(self):
        w=list(EXPECTED);w[2]=0x2402000e
        with self.assertRaises(ValueError): verify(w)
    def test_modified_branch_rejected(self):
        w=list(EXPECTED);w[5]=0x0441fffc
        with self.assertRaises(ValueError): verify(w)

if __name__=='__main__':unittest.main()
