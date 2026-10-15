import unittest
from tools.verify_record_return import EXPECTED, check

class RecordReturnTests(unittest.TestCase):
    def fixture(self):
        load, size = 0x80011420, 0xc1800
        data = bytearray(2048 + size)
        data[:8] = b'PS-X EXE'
        data[0x18:0x1c] = load.to_bytes(4, 'little')
        data[0x1c:0x20] = size.to_bytes(4, 'little')
        for pc, value in EXPECTED.items():
            i = 2048 + pc - load
            data[i:i+4] = value.to_bytes(4, 'little')
        return data

    def test_signature(self):
        self.assertEqual(check(self.fixture())['verified_words'], 7)
    def test_bad_return_register(self):
        data = self.fixture()
        data[2048+0x80078e48-0x80011420] ^= 1
        with self.assertRaises(ValueError): check(data)
    def test_bad_caller_copy(self):
        data = self.fixture()
        data[2048+0x800791c4-0x80011420] ^= 1
        with self.assertRaises(ValueError): check(data)
    def test_invalid_exe(self):
        with self.assertRaises(ValueError): check(b'bad')
    def test_truncated_exe(self):
        with self.assertRaises(ValueError): check(self.fixture()[:3000])

if __name__ == '__main__':
    unittest.main()
