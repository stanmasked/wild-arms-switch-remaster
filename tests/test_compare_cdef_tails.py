import unittest
from tools.compare_cdef_tails import compare_pair

class CDEFTailTests(unittest.TestCase):
    def test_different_tails(self):
        report = compare_pair(b'A'*6 + b'X'*2 + b'A'*6 + b'Y'*2, 0, 8, 8, 6)
        self.assertEqual(report['tail_different_bytes'], 2)
        self.assertEqual(report['identical_prefix_bytes'], 6)
        self.assertEqual(report['tail_status'], 'different')
        self.assertFalse(report['second_region_truncated'])

    def test_truncated_final_pair(self):
        report = compare_pair(b'A'*6+b'X'*2+b'A'*6, 0, 8, 8, 6)
        self.assertTrue(report['second_region_truncated'])
        self.assertEqual(report['tail_status'], 'unavailable')
        self.assertEqual(report['tail_comparable_bytes'], 0)

    def test_reject_wrong_common_prefix(self):
        with self.assertRaises(ValueError):
            compare_pair(b'AAAXXXXXAABYYYYY', 0, 8, 8, 4)

    def test_reject_short_input(self):
        with self.assertRaises(ValueError):
            compare_pair(b'A'*5, 0, 8, 8, 6)

    def test_identical_tails(self):
        report = compare_pair(b'ABCDEFFGABCDEFFG', 0, 8, 8, 6)
        self.assertEqual(report['tail_status'], 'identical_in_checked_range')
        self.assertEqual(report['identical_prefix_bytes'], 8)

if __name__ == '__main__':
    unittest.main()
