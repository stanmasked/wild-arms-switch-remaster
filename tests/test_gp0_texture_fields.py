import struct
import unittest
from tools.audit_gp0_texture_fields import (
    TEXTURE_FIELDS, audit_texture_fields, decode_store, scan_field_writes)


def sw(op, base=11, source=1, off=12):
    return (op << 26) | (base << 21) | (source << 16) | (off & 0xffff)


class TextureFields(unittest.TestCase):
    def test_expected_uv_clut_tpage_word_positions(self):
        self.assertEqual(TEXTURE_FIELDS['FT3'], (12, 20, 28))
        self.assertEqual(TEXTURE_FIELDS['GT3'], (12, 24, 36))

    def test_store_decoder(self):
        self.assertEqual(decode_store(sw(0x29, off=-4))['size'], 2)
        self.assertEqual(decode_store(sw(0x3a, off=36))['instruction'], 'SWC2')
        self.assertIsNone(decode_store(sw(0x23)))

    def test_overlapping_byte_halfword_fullword(self):
        words = [sw(0x28, off=15), sw(0x29, off=23), sw(0x2b, off=36)]
        result = scan_field_writes(struct.pack('<3I', *words), 0, 0, 12, 11,
                                   TEXTURE_FIELDS['GT3'])
        self.assertEqual([x['overlaps'] for x in result],
                         [['UV0_CLUT_TPAGE'], ['UV1_CLUT_TPAGE'], ['UV2_CLUT_TPAGE']])

    def test_wrong_packet_base_ignored(self):
        self.assertEqual(scan_field_writes(struct.pack('<I',sw(0x2b,12,1,12)),
                                           0,0,4,11,(12,20,28)), [])

    def test_coordinates_and_color_fields_do_not_overlap_uv(self):
        words = [sw(0x3a,off=i) for i in (4, 8, 16, 20, 28, 32)]
        self.assertEqual(scan_field_writes(struct.pack('<6I',*words),0,0,24,11,
                                           TEXTURE_FIELDS['GT3']),[])

    def test_delay_slot_exclusion(self):
        words = [sw(0x2b,off=12),0]
        self.assertEqual(scan_field_writes(struct.pack('<2I',*words),0,4,8,11,
                                           TEXTURE_FIELDS['GT3']),[])

    def test_invalid_range(self):
        self.assertEqual(scan_field_writes(b'\0'*8,0,0,12,11,(12,20,28)),[])

    def test_empty_executable(self):
        report = audit_texture_fields(b'',0)
        self.assertEqual(report['textured_packet_candidates'],0)
        self.assertEqual(report['initial_uv_values_recovered'],0)


if __name__=='__main__':
    unittest.main()
