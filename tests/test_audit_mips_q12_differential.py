"""Validate reproducible host Q12 arithmetic checks and safe audit metadata."""
import unittest
from tools.audit_mips_q12_differential import audit


class AuditMipsQ12DifferentialTests(unittest.TestCase):
    def test_all_three_synthetic_mips_schedules_checked(self):
        result = audit(cases=3)
        self.assertEqual(result['synthetic_comparisons_passed'], 9)
        self.assertEqual(set(result['schedules']),
                         {'single_product','dot3_shift_after_sum',
                          'dot3_shift_each_product'})

    def test_reproducible_seeded_report(self):
        self.assertEqual(audit(cases=5, seed=4), audit(cases=5, seed=4))

    def test_no_private_gameplay_claims(self):
        result = audit(cases=2)
        self.assertFalse(result['original_gameplay_coefficients_checked'])
        self.assertFalse(result['playstation_hardware_equivalence_proven'])
        self.assertFalse(result['game_assets_emitted'])
        self.assertNotIn('registers', str(result))

    def test_invalid_case_count_rejected(self):
        for n in (0, 10001, -1, 'four'):
            with self.subTest(n=n), self.assertRaises(ValueError):
                audit(cases=n)

    def test_invalid_seed_rejected(self):
        for n in (-1, 1 << 32, 'random'):
            with self.subTest(n=n), self.assertRaises(ValueError):
                audit(cases=1, seed=n)

    def test_different_seed_same_counts(self):
        a, b = audit(cases=4, seed=7), audit(cases=4, seed=8)
        self.assertEqual(a['synthetic_comparisons_passed'],
                         b['synthetic_comparisons_passed'])

if __name__ == '__main__':
    unittest.main()
