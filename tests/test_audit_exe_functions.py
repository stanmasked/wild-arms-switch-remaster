import unittest
from tools.audit_exe_functions import kind, inspect, exe_info

class AuditTests(unittest.TestCase):
    def fixture(self):
        b = bytearray(2048 + 32)
        b[:8] = b'PS-X EXE'
        b[0x18:0x1c] = (0x80010000).to_bytes(4, 'little')
        b[0x1c:0x20] = (32).to_bytes(4, 'little')
        for i, w in enumerate((0x00051080, 0x00451021, 0xac640a44, 0x03e00008)):
            b[2048+4*i:2052+4*i] = w.to_bytes(4, 'little')
        return bytes(b)

    def test_categories(self):
        self.assertEqual([kind(v) for v in (0x03e00008, 0xac640a44, 0x8c632c3c, 0x0c01b496)],
                         ['jr_ra', 'store', 'load', 'jal'])

    def test_function(self):
        r = inspect(self.fixture(), [0x80010000], 16)[0]
        self.assertEqual(r['first_jr_ra'], '0x8001000c')
        self.assertEqual(r['iso_exe_file_offset'], 2048)
        self.assertTrue(r['shared_index_prefix'])

    def test_bad_window(self):
        with self.assertRaises(ValueError):
            inspect(self.fixture(), [0x80010000], 3)

    def test_bad_header(self):
        with self.assertRaises(ValueError):
            exe_info(b'bad')

    def test_bad_address(self):
        with self.assertRaises(ValueError):
            inspect(self.fixture(), [0x80020000])

if __name__ == '__main__':
    unittest.main()
