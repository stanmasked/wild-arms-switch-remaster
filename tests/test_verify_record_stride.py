import unittest
from tools.verify_record_stride import INDEX_WORDS, GLOBAL_WORDS, stride_from_index_words, inspect_exe

class RecordStrideTests(unittest.TestCase):
    def test_mips_arithmetic(self):
        self.assertEqual(stride_from_index_words(INDEX_WORDS), 364)

    def test_changed_opcode_rejected(self):
        x = list(INDEX_WORDS)
        x[0] = 0
        with self.assertRaises(ValueError):
            stride_from_index_words(x)

    def test_three_function_prefixes(self):
        base = 0x80011420
        data = bytearray(2048 + 0xc1800)
        data[:8] = b'PS-X EXE'
        data[0x18:0x1c] = base.to_bytes(4, 'little')
        data[0x1c:0x20] = (0xc1800).to_bytes(4, 'little')
        for target in (0x8006d258, 0x8006dca0, 0x8006dcec):
            offset = 2048 + target - base
            for i, w in enumerate(INDEX_WORDS + GLOBAL_WORDS):
                data[offset + 4*i:offset + 4*i+4] = w.to_bytes(4, 'little')
        rows = inspect_exe(data)
        self.assertEqual(len(rows), 3)
        self.assertEqual([x['stride_bytes'] for x in rows], [364]*3)

    def test_invalid_executable(self):
        with self.assertRaises(ValueError):
            inspect_exe(b'invalid')

if __name__ == '__main__':
    unittest.main()
