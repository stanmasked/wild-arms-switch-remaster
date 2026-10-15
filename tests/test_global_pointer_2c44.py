"""Synthetic regression tests for adjacent accesses to 0x800D2C44.

No PlayStation image is required in CI.
"""
import unittest
from tools.find_global_refs import scan_pairs

TARGET = 0x800D2C44

def words(*values):
    return b''.join(x.to_bytes(4, 'little') for x in values)

class Global2C44Tests(unittest.TestCase):
    def test_actual_load_instruction_shape(self):
        actual = words(0x3C10800D, 0x8E102C44)
        found = scan_pairs(actual, 0x80010000, TARGET)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['kind'], 'load')
        self.assertEqual(found[0]['memory_pc'], '0x80010004')

    def test_store_detection(self):
        found = scan_pairs(words(0x3C03800D, 0xAC622C44), 0, TARGET)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['kind'], 'store')

    def test_wrong_register(self):
        self.assertEqual(scan_pairs(words(0x3C10800D, 0x8E522C44), 0, TARGET), [])

    def test_unrelated_global(self):
        self.assertEqual(scan_pairs(words(0x3C10800D, 0x8E102C3C), 0, TARGET), [])

    def test_nonadjacent_not_reported(self):
        self.assertEqual(scan_pairs(words(0x3C10800D, 0, 0x8E102C44), 0, TARGET), [])

if __name__ == '__main__':
    unittest.main()
