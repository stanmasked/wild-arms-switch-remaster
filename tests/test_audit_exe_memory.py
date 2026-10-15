import unittest
from tools.audit_exe_memory import parse_header

def header(load=0x80011420, size=0xc1800, bss=0, bss_size=0):
    h = bytearray(2048)
    h[:8] = b'PS-X EXE'
    for offset, word in ((0x18, load), (0x1c, size), (0x28, bss), (0x2c, bss_size)):
        h[offset:offset+4] = word.to_bytes(4, 'little')
    return h

class EXEMemoryTests(unittest.TestCase):
    def test_no_declared_bss(self):
        r = parse_header(header())
        self.assertFalse(r['declared_bss'])
        self.assertFalse(r['target_in_declared_bss'])
        self.assertEqual(r['target_distance_from_image_end'], 28)

    def test_declared_bss(self):
        r = parse_header(header(bss=0x800d2c20, bss_size=128))
        self.assertTrue(r['declared_bss'])
        self.assertTrue(r['target_in_declared_bss'])

    def test_image_end_exclusive(self):
        r = parse_header(header(), target=0x800d2c20)
        self.assertFalse(r['target_in_load_image'])

    def test_invalid_header(self):
        with self.assertRaises(ValueError):
            parse_header(b'not a PSX exe')

    def test_zero_load(self):
        with self.assertRaises(ValueError):
            parse_header(header(size=0))

if __name__ == '__main__':
    unittest.main()
