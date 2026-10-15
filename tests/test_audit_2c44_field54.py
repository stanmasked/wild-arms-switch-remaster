import unittest
from tools.audit_2c44_field54 import SIGNATURES, check_signature

class Field54SignatureTests(unittest.TestCase):
    def fixture(self):
        load, size = 0x80011420, 0xc1800
        exe = bytearray(2048 + size)
        exe[:8] = b'PS-X EXE'
        exe[0x18:0x1c] = load.to_bytes(4, 'little')
        exe[0x1c:0x20] = size.to_bytes(4, 'little')
        for address, instruction in SIGNATURES.items():
            i = 2048 + address - load
            exe[i:i+4] = instruction.to_bytes(4, 'little')
        return exe

    def test_signature(self):
        self.assertEqual(check_signature(self.fixture())['verified_instruction_count'], 15)
    def test_three_field_reads(self):
        self.assertEqual(len(check_signature(self.fixture())['field_54_read_pcs']), 3)
    def test_changed_word_rejected(self):
        exe = self.fixture()
        exe[2048+0x80078f8c-0x80011420] ^= 1
        with self.assertRaises(ValueError): check_signature(exe)
    def test_bad_exe(self):
        with self.assertRaises(ValueError): check_signature(b'invalid')
    def test_truncated(self):
        with self.assertRaises(ValueError): check_signature(self.fixture()[:4096])

if __name__ == '__main__':
    unittest.main()
