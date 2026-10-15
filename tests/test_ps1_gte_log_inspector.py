import unittest
from tools.inspect_ps1_gte_log import inspect

class InspectGteLog(unittest.TestCase):
    def test_real_test_all_summary_shape(self):
        output = inspect('gte/test-all\nAuto test all GTE valid opcodes/registers\nPassed tests: 1150\nFailed tests: 0\nDone.\n')
        self.assertEqual(output['kind'], 'summary_only')
        self.assertEqual(output['passed'], 1150)
        self.assertEqual(output['failed'], 0)
        self.assertEqual(output['rtps_vectors'], 0)
        self.assertFalse(output['importable'])

    def test_failed_summary_is_not_a_fixture(self):
        output = inspect('Passed tests: 1149\nFailed tests: 1\n')
        self.assertEqual(output['failed'], 1)
        self.assertFalse(output['importable'])

    def test_register_lines_are_insufficient(self):
        output = inspect('Input:\n> r[0] = 0x12345678\n> r[1] = 0x00000000\n')
        self.assertEqual(output['kind'], 'partial_register_log')
        self.assertEqual(output['register_lines'], 2)
        self.assertFalse(output['importable'])

    def test_unrecognized_is_not_imported(self):
        self.assertEqual(inspect('Passed tests: none')['kind'], 'unrecognized')

    def test_summary_plus_register_lines_not_summary(self):
        report = inspect('Passed tests: 1150\nFailed tests: 0\n> r[5] = 0x00000000\n')
        self.assertEqual(report['kind'], 'partial_register_log')

if __name__ == '__main__':
    unittest.main()
