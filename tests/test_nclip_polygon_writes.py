import struct
import unittest
from tools.audit_nclip_polygon_writes import describe, swc2

def swc2_word(rt, base=11, off=8):
    return (0x3a << 26) | (base << 21) | (rt << 16) | (off & 0xffff)

class NclipPolygonWrites(unittest.TestCase):
    def test_instruction_decode(self):
        self.assertEqual(swc2(swc2_word(12,11,-8)), (12,11,-8))
        self.assertIsNone(swc2(0xad690000))

    def test_positive_path_contains_fifo_triplet(self):
        words = [0x4b400006, 0x4809c000, 0x19200004, 0,
                 swc2_word(12,11,8), swc2_word(13,11,16),
                 swc2_word(14,11,24), 0]
        result = describe(struct.pack('<8I', *words),0x80010000)
        self.assertEqual(result['mac0_blez_with_sxy_triplet'],1)
        self.assertEqual([x['register'] for x in result['sites'][0]['sxy_stores']],
                         ['SXY0','SXY1','SXY2'])

    def test_branch_delay_slot_does_not_count(self):
        words = [0x4b400006,0x4809c000,0x19200004,swc2_word(12),
                 swc2_word(13),swc2_word(14),0,0]
        result = describe(struct.pack('<8I', *words),0x80010000)
        self.assertEqual(result['mac0_blez_with_sxy_triplet'],0)

    def test_negative_branch_target_ignored(self):
        words = [0x4b400006,0x4809c000,0x1920fffc,0,
                 swc2_word(12),swc2_word(13),swc2_word(14),0]
        result = describe(struct.pack('<8I', *words),0x80010000)
        self.assertEqual(result['mac0_blez_with_sxy_triplet'],0)

    def test_other_store_is_not_gte(self):
        words = [0x4b400006,0x4809c000,0x19200004,0,
                 0xad6c0008,0xad6d0010,0xad6e0018,0]
        result = describe(struct.pack('<8I', *words),0x80010000)
        self.assertEqual(result['mac0_blez_with_sxy_triplet'],0)

if __name__ == '__main__':
    unittest.main()
