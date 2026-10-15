import unittest
from tools.audit_cdef_calls import decode_jump, scan_region, audit

class CDEFCallTests(unittest.TestCase):
    def test_jal(self):
        self.assertEqual(decode_jump(0x0c01f559,0x8017c80c)['target'], '0x8007D564')
    def test_overlay_j(self):
        self.assertEqual(decode_jump(0x0805f310,0x8017c844)['target'], '0x8017CC40')
    def test_non_jump(self):
        self.assertIsNone(decode_jump(0x02402021,0x8017c7f8))
    def test_copy_equivalence(self):
        data = bytearray(0x40000)
        for start in (0x38000,0x3c000):
            data[start+0x7f8:start+0x7fc] = (0x0c01f559).to_bytes(4,'little')
            data[start+0x84c:start+0x850] = (0x0805f310).to_bytes(4,'little')
        self.assertTrue(audit(data)['copies_equal'])
    def test_truncation(self):
        with self.assertRaises(ValueError): scan_region(bytearray(5),0)

if __name__ == '__main__': unittest.main()
