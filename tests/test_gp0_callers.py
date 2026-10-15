import struct
import unittest
from tools.audit_gp0_callers import jal_target, a0_definition, direct_calls, find_nearby_a0, audit_callers

def jal(target):
    return (3 << 26) | ((target >> 2) & 0x03ffffff)

def lw_a0(base, offset):
    return (35 << 26) | (base << 21) | (4 << 16) | (offset & 0xffff)

class GP0CallerAudit(unittest.TestCase):
    def test_direct_jal_target(self):
        self.assertEqual(jal_target(jal(0x80066dc8), 0x80076adc), 0x80066dc8)
        self.assertIsNone(jal_target(0x08019b72, 0x80076adc))

    def test_region_comes_from_call_pc(self):
        self.assertEqual(jal_target(jal(0x90001234), 0x90002000), 0x90001234)

    def test_lw_a0_from_structure(self):
        self.assertEqual(a0_definition(lw_a0(17,16)),
                         {'kind':'LW','base_register':17,'offset':16})
        self.assertEqual(a0_definition(lw_a0(16,-4))['offset'],-4)

    def test_negative_addiu_immediate(self):
        word=(9<<26)|(4<<21)|(4<<16)|0xfffc
        self.assertEqual(a0_definition(word)['immediate'],-4)

    def test_non_a0_write_ignored(self):
        self.assertIsNone(a0_definition((35<<26)|(17<<21)|(5<<16)|16))

    def test_addu_a0_and_unknown_source_are_explicit(self):
        word=(22<<21)|(4<<11)|0x21
        self.assertEqual(a0_definition(word),
                         {'kind':'ADDU','source_registers':[22,0]})

    def test_multiple_calls_same_target(self):
        base=0x80012000
        image=struct.pack('<5I',jal(base+0x10),0,jal(base+0x10),0,0)
        self.assertEqual(direct_calls(image,base)[base+0x10],[base,base+8])

    def test_nearest_textual_a0_write(self):
        base=0x80012000
        image=struct.pack('<5I',lw_a0(17,16),0,lw_a0(16,20),0,jal(base))
        self.assertEqual(find_nearby_a0(image,base,base+16)['offset'],20)
        self.assertIsNone(find_nearby_a0(image,base,base))

    def test_empty_image_does_not_guess_callers(self):
        result=audit_callers(b'',0)
        self.assertEqual(result['packet_paths'],0)
        self.assertEqual(result['paths_with_direct_jal_candidate'],0)
        self.assertFalse(result['runtime_pointer_contents_known'])

if __name__=='__main__':unittest.main()
