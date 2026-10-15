import struct
import unittest
from tools.audit_gp0_color_fifo import COLOR_OFFSETS, decode_swc2, scan_rgb_writes, audit_colors

def swc2(gte, base=11, offset=4):
    return (0x3a << 26) | (base << 21) | (gte << 16) | (offset & 65535)

class ColorFifoAudit(unittest.TestCase):
    def test_rgb_register_and_offset_decoder(self):
        self.assertEqual(decode_swc2(swc2(20, 11, -8)),
                         {'base': 11, 'gte_register': 20, 'offset': -8})
        self.assertIsNone(decode_swc2(0xad6c0004))

    def test_gt3_rgb_triplet(self):
        words = [0x19200005, 0, swc2(20,11,4), swc2(21,11,16),
                 swc2(22,11,28), 0, 0]
        stores = scan_rgb_writes(struct.pack('<7I', *words),0,0,28,11)
        self.assertEqual(tuple(x['offset'] for x in stores), COLOR_OFFSETS['GT3'])
        self.assertEqual([x['register'] for x in stores],['RGB0','RGB1','RGB2'])

    def test_non_packet_register_ignored(self):
        words = [0, 0, swc2(20,12,4), swc2(21,11,16), swc2(22,11,28)]
        stores = scan_rgb_writes(struct.pack('<5I',*words),0,0,20,11)
        self.assertEqual(len(stores),2)

    def test_delay_slot_not_counted(self):
        words = [swc2(20,11,4),swc2(21,11,16),swc2(22,11,28)]
        stores = scan_rgb_writes(struct.pack('<3I',*words),0,0,12,11)
        self.assertEqual([x['register'] for x in stores],['RGB2'])

    def test_out_of_range_branch_returns_empty(self):
        self.assertEqual(scan_rgb_writes(b'\0'*12,0,0,16,11),[])
        self.assertEqual(scan_rgb_writes(b'\0'*12,0,8,12,11),[])

    def test_empty_image_no_matches(self):
        self.assertEqual(audit_colors(b'',0)['counts']['matching_rgb_fifo_triplets'],0)

if __name__ == '__main__':
    unittest.main()
