"""Differential tests: independent Python fixed-point oracle vs MIPS execution."""
import random
import unittest

from tools.mips_q12_differential import (
    build_nine_product_program, build_nine_dot3_program, replay,
    reference_product_outputs, reference_dot3_outputs,
)
from tools.mips_q12_arithmetic_reference import mult_hi_lo
from tools.mips_integer_step import step

EDGES = (0, 1, 2, 4095, 4096, 4097, 32767, 32768, 65535,
         0xf000, 0xe000, 0x8001)

class MipsQ12DifferentialTests(unittest.TestCase):
    def test_product_program_has_exactly_nine_halfword_stores(self):
        words = build_nine_product_program()
        self.assertEqual(len(words), 63)
        self.assertEqual(sum(word >> 26 == 41 for word in words), 9)

    def test_signed_product_edge_vectors_against_independent_oracle(self):
        code = build_nine_product_program()
        pairs = [(a,b) for a in EDGES for b in EDGES]
        for index in range(0, len(pairs), 9):
            batch = (pairs[index:index+9] + pairs[:9])[:9]
            left, right = zip(*batch)
            with self.subTest(start=index):
                self.assertEqual(replay(code, left, right),
                                 reference_product_outputs(left, right))

    def test_signed_product_deterministic_random_vectors(self):
        rng = random.Random(206)
        code = build_nine_product_program()
        for case in range(120):
            left = [rng.getrandbits(16) for _ in range(9)]
            right = [rng.getrandbits(16) for _ in range(9)]
            with self.subTest(case=case):
                self.assertEqual(replay(code, left, right),
                                 reference_product_outputs(left, right))

    def test_pre_shift_dot3_edges_against_independent_oracle(self):
        rng = random.Random(1206)
        code = build_nine_dot3_program()
        for case in range(75):
            left = [rng.choice(EDGES) for _ in range(27)]
            right = [rng.choice(EDGES) for _ in range(27)]
            with self.subTest(case=case):
                self.assertEqual(replay(code, left, right),
                                 reference_dot3_outputs(left, right))

    def test_post_shift_dot3_edges_against_independent_oracle(self):
        rng = random.Random(2206)
        code = build_nine_dot3_program(shift_each=True)
        for case in range(75):
            left = [rng.choice(EDGES) for _ in range(27)]
            right = [rng.choice(EDGES) for _ in range(27)]
            with self.subTest(case=case):
                self.assertEqual(replay(code, left, right),
                                 reference_dot3_outputs(left, right, shift_each=True))

    def test_shift_placement_changes_negative_fractional_rounding(self):
        left = [0xffff] * 27
        right = [1] * 27
        before = replay(build_nine_dot3_program(),left,right)
        after = replay(build_nine_dot3_program(shift_each=True),left,right)
        self.assertEqual(before, (-1,)*9)
        self.assertEqual(after, (-3,)*9)

    def test_overflow_order_is_integer_not_float(self):
        a = [0x8000] * 27
        b = [0x8000] * 27
        output = replay(build_nine_dot3_program(), a, b)
        self.assertEqual(output, reference_dot3_outputs(a, b))
        self.assertEqual(output, (0,)*9)

    def test_hi_lo_full_32bit_signed_and_unsigned_mult(self):
        samples=[(0xffffffff,2),(0x80000000,0x80000000),
                 (0x80000000,3),(0x7fffffff,0xffffffff),
                 (0xffffffff,0xffffffff),(0x12345678,0x7fffffff)]
        for a,b in samples:
            registers=[0]*32
            registers[8],registers[9]=a,b
            for function, signed in ((24,True),(25,False)):
                opcode=(8<<21)|(9<<16)|function
                _,hi,lo=step(opcode,registers)
                with self.subTest(a=a,b=b,signed=signed):
                    self.assertEqual((hi,lo),mult_hi_lo(a,b,signed=signed))

    def test_invalid_operands_rejected_instead_of_wrapped_silently(self):
        with self.assertRaises(ValueError):
            replay(build_nine_product_program(),[65536]*9,[1]*9)
        with self.assertRaises(ValueError):
            replay(build_nine_product_program(),[1]*8,[1]*8)

    def test_oracle_wrong_length_rejected(self):
        with self.assertRaises(ValueError):
            reference_product_outputs([0],[0])
        with self.assertRaises(ValueError):
            reference_dot3_outputs([0]*9,[0]*9)

if __name__ == '__main__':
    unittest.main()
