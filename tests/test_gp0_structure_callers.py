import struct
import unittest
from tools.audit_gp0_structure_callers import (
    decode_argument_a0, last_argument_write, audit)


def addiu_a0(source, offset):
    return (9<<26)|(source<<21)|(4<<16)|(offset&0xffff)


def addu_a0(source):
    return (source<<21)|(4<<11)|0x21


def jal(target):
    return (3<<26)|((target>>2)&0x3ffffff)


class StructureCallerTests(unittest.TestCase):
    def test_a0_addiu_unsigned_encoding_signed_value(self):
        self.assertEqual(decode_argument_a0(addiu_a0(20,-92))['signed_displacement'],-92)

    def test_a0_addiu_positive_structure_strides(self):
        self.assertEqual(decode_argument_a0(addiu_a0(20,92))['signed_displacement'],92)
        self.assertEqual(decode_argument_a0(addiu_a0(20,140))['signed_displacement'],140)

    def test_a0_copy_register(self):
        self.assertEqual(decode_argument_a0(addu_a0(22)),
                         {'kind':'ADDU','source_registers':[22,0]})

    def test_not_an_a0_write(self):
        self.assertIsNone(decode_argument_a0((9<<26)|(20<<21)|(5<<16)|92))

    def test_real_jal_instruction_decoding(self):
        base=0x80010000
        image=struct.pack('<3I',addiu_a0(20,92),jal(base+8),0)
        result=audit(image,base,targets=(base+8,))
        self.assertEqual(result['direct_jal_calls'],1)
        self.assertEqual(result['records'][0]['calls'][0]['last_a0_definition']['signed_displacement'],92)

    def test_delay_slot_is_not_argument_source_for_pre_call_lookup(self):
        base=0x80010000
        image=struct.pack('<4I',addu_a0(22),jal(base+12),addiu_a0(20,140),0)
        self.assertEqual(last_argument_write(image,base,base+4)['kind'],'ADDU')

    def test_nearest_wins(self):
        base=0x80010000
        image=struct.pack('<4I',addiu_a0(20,92),addiu_a0(20,140),jal(base+12),0)
        self.assertEqual(last_argument_write(image,base,base+8)['signed_displacement'],140)

    def test_outside_image_rejected(self):
        with self.assertRaises(ValueError):last_argument_write(b'\0'*8,0x80010000,0x8001000c)

    def test_unresolved_target_does_not_fabricate_call(self):
        report=audit(b'\0'*16,0x80010000,targets=(0x80012000,))
        self.assertEqual(report['direct_jal_calls'],0)
        self.assertFalse(report['runtime_structure_data_recovered'])

if __name__=='__main__':unittest.main()
