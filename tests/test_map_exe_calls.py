import unittest
from tools.map_exe_calls import parse_psx_exe, map_jump, scan

class ExeMapTests(unittest.TestCase):
    def setUp(self):
        h = bytearray(2048)
        h[:8] = b'PS-X EXE'
        for o, v in ((0x10, 0x800b065c), (0x18, 0x80011420),
                     (0x1c, 0xc1800), (0x30, 0x801ffff0)):
            h[o:o+4] = v.to_bytes(4, 'little')
        self.exe = parse_psx_exe(h)

    def test_header(self):
        self.assertEqual(self.exe['load_end_exclusive'], 0x800d2c20)
        self.assertEqual(self.exe['entry'], 0x800b065c)

    def test_invalid_header(self):
        with self.assertRaises(ValueError):
            parse_psx_exe(b'bad')

    def test_exe_call(self):
        w = (3 << 26) | ((0x8006d258 >> 2) & 0x03ffffff)
        c = map_jump(w, 0x9c, 0x8017c000, self.exe)
        self.assertEqual(c['target'], '0x8006d258')
        self.assertEqual(c['location'], 'main_exe')
        self.assertEqual(c['exe_iso_file_offset'], 2048 + 0x8006d258 - 0x80011420)

    def test_overlay_jump(self):
        w = (2 << 26) | ((0x8017c300 >> 2) & 0x03ffffff)
        self.assertEqual(map_jump(w, 0xf4, 0x8017c000, self.exe)['location'],
                         'overlay_candidate')

    def test_non_jump(self):
        self.assertIsNone(map_jump(0x27bdffa0, 0x1c, 0x8017c000, self.exe))

    def test_scan(self):
        w = (3 << 26) | ((0x8006d258 >> 2) & 0x03ffffff)
        data = b'\x00'*4 + w.to_bytes(4, 'little') + b'\x00'*4
        self.assertEqual(len(scan(data, self.exe, 0x8017c000, 0, 12)), 1)

if __name__ == '__main__':
    unittest.main()
