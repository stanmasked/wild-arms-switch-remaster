import struct
import unittest
from tools.audit_original_nclip_winding import (
    is_command, mac0_move, blez_source, inspect, parse_exe)

class PolygonWindingAudit(unittest.TestCase):
    def test_cop2_flags_preserved(self):
        self.assertTrue(is_command(0x4b400006,6))
        self.assertTrue(is_command(0x4a280030,0x30))
        self.assertFalse(is_command(0x4a280030,6))

    def test_mac0_read_and_signed_branch(self):
        self.assertEqual(mac0_move(0x4809c000),9)
        self.assertEqual(blez_source(0x19200019),9)
        self.assertIsNone(mac0_move(0x4809b800))
        self.assertIsNone(blez_source(0x15200019))

    def test_synthetic_sequence(self):
        words=[0x4a280030,0x4b400006,0,0x4809c000,0,0x19200002,0,0,0]
        report=inspect(struct.pack('<9I',*words),0x80010000)
        self.assertEqual((report['rtpt_count'],report['nclip_count'],
                          report['nclip_with_mac0_blez']),(1,1,1))
        self.assertEqual(report['sites'][0]['branch_target'],'0x80010020')

    def test_unrelated_cop2_read(self):
        words=[0x4b400006,0x4809b800,0x19200004]
        report=inspect(struct.pack('<3I',*words),0)
        self.assertEqual(report['nclip_with_mac0_blez'],0)

    def test_exe_validation(self):
        header=bytearray(2048)
        header[:8]=b'PS-X EXE'
        struct.pack_into('<II',header,0x18,0x80011420,8)
        self.assertEqual(parse_exe(bytes(header)+b'12345678'),
                         (0x80011420,b'12345678'))
        with self.assertRaises(ValueError):parse_exe(bytes(header))
        with self.assertRaises(ValueError):parse_exe(b'bad')

if __name__=='__main__':unittest.main()
