import struct
import unittest
from tools.audit_gp0_matrix_arithmetic import classify, analyze

BASE = 0x80010000
START = BASE + 0x20

def r(rs, rt, rd, sa, fn):
    return rs << 21 | rt << 16 | rd << 11 | sa << 6 | fn

class ArithmeticDecodeTests(unittest.TestCase):
    def test_signed_mult(self):
        self.assertEqual(classify(r(8, 9, 0, 0, 24)), ('MULT', (8, 9)))
    def test_unsigned_mult(self):
        self.assertEqual(classify(r(8, 9, 0, 0, 25)), ('MULTU', (8, 9)))
    def test_mflo(self):
        self.assertEqual(classify(r(0, 0, 10, 0, 18)), ('MFLO', (10,)))
    def test_mfhi(self):
        self.assertEqual(classify(r(0, 0, 10, 0, 16)), ('MFHI', (10,)))
    def test_arithmetic_shift_right(self):
        self.assertEqual(classify(r(0, 9, 10, 12, 3)), ('SRA', (10, 9, 12)))
    def test_variable_arithmetic_shift(self):
        self.assertEqual(classify(r(7, 9, 10, 0, 7)), ('SRAV', (10, 9, 7)))
    def test_reject_invalid_mult_encoding(self):
        self.assertIsNone(classify(r(8, 9, 4, 0, 24)))
    def test_reject_nonzero_shift_source(self):
        self.assertIsNone(classify(r(8, 9, 10, 12, 3)))
    def test_reject_variable_shift_reserved_sa(self):
        self.assertIsNone(classify(r(7, 9, 10, 1, 7)))
    def test_report_synthetic(self):
        words = [r(8, 9, 0, 0, 24), r(0, 0, 10, 0, 18),
                 r(0, 10, 11, 12, 3), 0xffffffff]
        b = b'\x00' * 0x20 + struct.pack('<4I', *words)
        report = analyze(b, BASE, START, START + 12)
        self.assertTrue(report['valid_range'])
        self.assertEqual(report['counts'], {'MULT': 1, 'MFLO': 1, 'SRA': 1})
        self.assertFalse(report['coefficient_dataflow_proven'])
    def test_out_of_range(self):
        self.assertFalse(analyze(b'', BASE, START, START)['valid_range'])

if __name__ == '__main__':
    unittest.main()
