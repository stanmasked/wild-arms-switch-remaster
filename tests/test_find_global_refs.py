import unittest
from tools.find_global_refs import scan_pairs

class FindGlobalRefsTests(unittest.TestCase):
    def test_load(self):
        b = (0x3c03800d).to_bytes(4,'little') + (0x8c632c3c).to_bytes(4,'little')
        self.assertEqual([x['kind'] for x in scan_pairs(b,0x80010000,0x800d2c3c)], ['load'])
    def test_store(self):
        b = (0x3c03800d).to_bytes(4,'little') + (0xac622c3c).to_bytes(4,'little')
        self.assertEqual([x['kind'] for x in scan_pairs(b,0x80010000,0x800d2c3c)], ['store'])
    def test_wrong_register(self):
        b = (0x3c03800d).to_bytes(4,'little') + (0x8c422c3c).to_bytes(4,'little')
        self.assertEqual(scan_pairs(b,0,0x800d2c3c), [])
    def test_sign_extension(self):
        b = (0x3c03800e).to_bytes(4,'little') + (0x8c638000).to_bytes(4,'little')
        self.assertEqual(len(scan_pairs(b,0,0x800d8000)),1)
    def test_unaligned_code(self):
        with self.assertRaises(ValueError): scan_pairs(b'a',0,0x800d2c3c)
if __name__=='__main__': unittest.main()
