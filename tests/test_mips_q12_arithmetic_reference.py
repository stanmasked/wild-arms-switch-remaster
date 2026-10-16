"""Independent exact-integer oracle for explicit (not original-game) MIPS Q12 schedules."""
import unittest
from tools.mips_q12_arithmetic_reference import (
    signed16, signed32, mult_hi_lo, sh_q12_product, sh_q12_dot3,
)


class Q12ArithmeticReferenceTests(unittest.TestCase):
    def test_signed_halfword_extremes(self):
        self.assertEqual([signed16(n) for n in (0, 0x7fff, 0x8000, 0xffff)],
                         [0, 32767, -32768, -1])

    def test_signed_register_extremes(self):
        self.assertEqual([signed32(n) for n in (0, 0x7fffffff, 0x80000000, 0xffffffff)],
                         [0, 2147483647, -2147483648, -1])

    def test_signed_mult_hi_lo_negative(self):
        self.assertEqual(mult_hi_lo(0xffffffff, 2), (0xffffffff, 0xfffffffe))
        self.assertEqual(mult_hi_lo(0x80000000, 2), (0xffffffff, 0))
        self.assertEqual(mult_hi_lo(0x80000000, 0x80000000), (0x40000000, 0))

    def test_unsigned_mult_hi_lo_distinguishes_sign(self):
        self.assertEqual(mult_hi_lo(0xffffffff, 2, signed=False), (1, 0xfffffffe))
        self.assertEqual(mult_hi_lo(0x80000000, 2, signed=False), (1, 0))

    def test_exact_unity_product(self):
        self.assertEqual(sh_q12_product(4096, 4096), 4096)
        self.assertEqual(sh_q12_product(0xf000, 4096), 0xf000)
        self.assertEqual(sh_q12_product(0xf000, 0xf000), 4096)

    def test_negative_sra_rounds_toward_minus_infinity(self):
        # -1 >> 12 is -1 on MIPS SRA; rounding toward zero would be 0.
        self.assertEqual(sh_q12_product(0xffff, 1), 0xffff)
        self.assertEqual(sh_q12_product(0xffff, 4095), 0xffff)
        self.assertEqual(sh_q12_product(0xffff, 4096), 0xffff)

    def test_mflo_sra_sh_truncates_to_halfword(self):
        self.assertEqual(sh_q12_product(0x8000, 0x8000), 0x0000)
        self.assertEqual(sh_q12_product(0x7fff, 0x7fff), 0xfff0)

    def test_dot3_add_before_sra_differs_from_shift_each(self):
        # Each -1*1 >>12 is -1, but the sum of three -1 products >>12 is -1.
        a, b = [0xffff] * 3, [1] * 3
        self.assertEqual(sh_q12_dot3(a, b), 0xffff)
        self.assertEqual(sh_q12_dot3(a, b, shift_each=True), 0xfffd)

    def test_dot3_handles_32bit_addu_overflow(self):
        a = [0x8000] * 3
        b = [0x8000] * 3
        self.assertEqual(sh_q12_dot3(a,b), 0x0000)
        self.assertEqual(sh_q12_dot3(a,b,shift_each=True), 0x0000)

    def test_dot3_rejects_wrong_vector_lengths(self):
        with self.assertRaises(ValueError):
            sh_q12_dot3([1,2],[1,2])

    def test_halfword_oracle_rejects_non_halfwords(self):
        for n in (-1, 65536, 1.5, None):
            with self.subTest(value=n), self.assertRaises(ValueError):
                signed16(n)

if __name__ == '__main__':
    unittest.main()
