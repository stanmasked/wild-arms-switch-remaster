import unittest
from tools.audit_gp0_triangle_layouts import TRIANGLES, identify_layout, inspect_layouts

def stores(offsets, base=11):
    return [{'register': f'SXY{i}', 'offset': offset, 'base_register': base}
            for i, offset in enumerate(offsets)]

class GP0TriangleLayouts(unittest.TestCase):
    def test_four_real_layout_lengths(self):
        for words,(family,offsets,commands) in TRIANGLES.items():
            with self.subTest(words=words):
                result=identify_layout(words,stores(offsets),11)
                self.assertEqual(result['layout_candidate'],family)
                self.assertEqual(len(result['expected_gp0_opcode_range']),4)
                self.assertFalse(result['opcode_verified'])
                self.assertIsNone(result['observed_gp0_opcode'])

    def test_ambiguous_word_count_without_matching_offsets(self):
        self.assertIsNone(identify_layout(7,stores((8,20,32)),11)['layout_candidate'])

    def test_wrong_packet_base_rejected(self):
        self.assertIsNone(identify_layout(9,stores((8,20,32),12),11)['layout_candidate'])

    def test_missing_duplicate_and_extra_sxy_rejected(self):
        good=stores((8,12,16))
        for invalid in (good[:-1],good+[good[0]],[good[0],good[0],good[2]]):
            self.assertIsNone(identify_layout(4,invalid,11)['layout_candidate'])

    def test_unknown_length_does_not_assume_triangle(self):
        self.assertIsNone(identify_layout(5,stores((8,12,16)),11)['layout_candidate'])

    def test_empty_image_has_no_layout_matches(self):
        self.assertEqual(inspect_layouts(b'',0)['layout_matched'],0)

if __name__=='__main__':
    unittest.main()
