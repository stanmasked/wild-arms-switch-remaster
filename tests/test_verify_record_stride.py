import unittest
from tools.verify_record_stride import INDEX_WORDS, GLOBAL_WORDS, stride_from_index_words, inspect_exe

class RecordStrideTests(unittest.TestCase):
    def test_mips_arithmetic_exposes_unresolved_stride_discrepancy(self):
        # The checked-in eight instruction words evaluate to 677 index
        # units, and the subsequent SLL by 2 makes 2708, *not* 364.
        self.assertEqual(stride_from_index_words(INDEX_WORDS), 2708)
        self.assertNotEqual(stride_from_index_words(INDEX_WORDS), 364)
        self.assertEqual((INDEX_WORDS[4] >> 6) & 31, 3)

    def test_changed_opcode_rejected(self):
        x = list(INDEX_WORDS)
        x[0] = 0
        with self.assertRaises(ValueError):
            stride_from_index_words(x)

    def test_three_function_prefixes_do_not_certify_false_stride(self):
        base = 0x80011420
        data = bytearray(2048 + 0xc1800)
        data[:8] = b'PS-X EXE'
        data[0x18:0x1c] = base.to_bytes(4, 'little')
        data[0x1c:0x20] = (0xc1800).to_bytes(4, 'little')
        for target in (0x8006d258, 0x8006dca0, 0x8006dcec):
            offset = 2048 + target - base
            for i, w in enumerate(INDEX_WORDS + GLOBAL_WORDS):
                data[offset + 4*i:offset + 4*i+4] = w.to_bytes(4, 'little')
        # Matching opcodes alone cannot prove the legacy constant.
        with self.assertRaisesRegex(ValueError, 'unverified record stride'):
            inspect_exe(data)

    def test_invalid_executable(self):
        with self.assertRaises(ValueError):
            inspect_exe(b'invalid')

if __name__ == '__main__':
    unittest.main()
