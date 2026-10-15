import unittest
from tools.scan_global_dataflow import scan

def words(*xs):
    return b''.join(w.to_bytes(4, 'little') for w in xs)

class DataflowTests(unittest.TestCase):
    def test_adjacent_load(self):
        r = scan(words(0x3c03800d, 0x8c632c3c), 0x80010000)
        self.assertEqual([(x['kind'], x['instructions_from_lui']) for x in r], [('load', 1)])
    def test_nonadjacent_store(self):
        r = scan(words(0x3c03800d, 0, 0xac622c3c), 0x80010000)
        self.assertEqual([(x['kind'], x['instructions_from_lui']) for x in r], [('store', 2)])
    def test_killed_register(self):
        self.assertEqual(scan(words(0x3c03800d, 0x24030000, 0xac622c3c), 0), [])
    def test_branch_barrier(self):
        self.assertEqual(scan(words(0x3c03800d, 0x10000001, 0xac622c3c), 0), [])
    def test_addiu_address(self):
        self.assertEqual(len(scan(words(0x3c03800d, 0x24632c00, 0xac62003c), 0)), 1)
    def test_ori_address(self):
        self.assertEqual(len(scan(words(0x3c03800d, 0x34632c3c, 0xac620000), 0)), 1)
    def test_signed_offset(self):
        self.assertEqual(len(scan(words(0x3c03800e, 0x8c638000), 0, 0x800d8000)), 1)

if __name__ == '__main__':
    unittest.main()
