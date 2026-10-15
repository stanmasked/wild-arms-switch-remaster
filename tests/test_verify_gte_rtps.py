import unittest
from tools.verify_gte_rtps import EXPECTED,inspect_words

class GTERTPSTests(unittest.TestCase):
    def test_signature(self):
        self.assertEqual(inspect_words(EXPECTED)['command'],'RTPS')
    def test_flags(self):
        result=inspect_words(EXPECTED)
        self.assertEqual((result['sf'],result['lm']),(1,0))
    def test_outputs(self):
        result=inspect_words(EXPECTED)
        self.assertEqual(result['output_sxy2'],'memory32[a1]')
        self.assertEqual(result['output_ir0'],'memory32[a2]')
        self.assertEqual(result['output_flag'],'memory32[a3]')
    def test_return_delay_slot(self):
        self.assertTrue(inspect_words(EXPECTED)['return_delay_slot'])
    def test_mutation(self):
        words=list(EXPECTED);words[3]^=1
        with self.assertRaises(ValueError):inspect_words(words)
    def test_truncation(self):
        with self.assertRaises(ValueError):inspect_words(EXPECTED[:-1])

if __name__=='__main__':unittest.main()
