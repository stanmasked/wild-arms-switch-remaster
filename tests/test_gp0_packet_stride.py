import struct
import unittest
from tools.audit_gp0_packet_stride import (
    decode_packet_alias, decode_advance, inspect_stride, audit_packet_stride)

def addu(dest,rs,rt=0):
    return (rs<<21)|(rt<<16)|(dest<<11)|0x21

def advance(op,value):
    return (op<<26)|(4<<21)|(4<<16)|(value&65535)

class PacketStrideAudit(unittest.TestCase):
    def test_alias_decoder_requires_exact_packet_and_argument(self):
        self.assertTrue(decode_packet_alias(addu(11,4)))
        self.assertTrue(decode_packet_alias(addu(11,0,4)))
        self.assertFalse(decode_packet_alias(addu(10,4)))
        self.assertFalse(decode_packet_alias(addu(11,5)))

    def test_both_addi_and_addiu(self):
        self.assertEqual(decode_advance(advance(8,92)),92)
        self.assertEqual(decode_advance(advance(9,76)),76)
        self.assertIsNone(decode_advance(advance(9,-1)))
        self.assertIsNone(decode_advance(advance(8,0)))

    def test_six_original_strides(self):
        for stride in (92,92,76,76,52,68):
            words=[addu(11,4),advance(8,stride),0,0x4b400006]
            data=struct.pack('<4I',*words)
            result=inspect_stride(data,0x80010000,0x8001000c)
            self.assertEqual(result['stride_bytes'],stride)
            self.assertEqual(result['packet_cpu_register'],'r11')

    def test_wrong_pointer_does_not_match(self):
        data=struct.pack('<3I',addu(10,4),advance(8,92),0x4b400006)
        self.assertIsNone(inspect_stride(data,0,8))

    def test_negative_and_zero_advance_not_accepted(self):
        for value in (-4,0):
            data=struct.pack('<3I',addu(11,4),advance(8,value),0x4b400006)
            self.assertIsNone(inspect_stride(data,0,8))

    def test_lookback_interval(self):
        words=[addu(11,4),advance(8,92)]+[0]*10+[0x4b400006]
        data=struct.pack(f'<{len(words)}I',*words)
        self.assertIsNone(inspect_stride(data,0,(len(words)-1)*4,lookback=3))
        self.assertIsNotNone(inspect_stride(data,0,(len(words)-1)*4,lookback=16))

    def test_empty_input(self):
        self.assertEqual(audit_packet_stride(b'',0)['packet_pointer_matches'],0)

if __name__=='__main__':
    unittest.main()
