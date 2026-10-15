import unittest
from tools.audit_overlay_global_refs import scan_pairs, common_prefix, DEFAULT_TARGET

def pack(*words):
    return b''.join(word.to_bytes(4,'little') for word in words)

class OverlayGlobalReferenceTests(unittest.TestCase):
    def test_read(self):
        self.assertEqual(scan_pairs(pack(0x3c03800d,0x8c632c3c)),
                         [{'offset':0,'kind':'load'}])

    def test_store(self):
        self.assertEqual(scan_pairs(pack(0x3c03800d,0xac622c3c)),
                         [{'offset':0,'kind':'store'}])

    def test_wrong_register(self):
        self.assertEqual(scan_pairs(pack(0x3c03800d,0x8c422c3c)),[])

    def test_match_not_word_aligned_to_byte_offset(self):
        hits=scan_pairs(pack(0,0x3c03800d,0x8c632c3c))
        self.assertEqual(hits[0]['offset'],4)

    def test_signed_low_half(self):
        self.assertEqual(len(scan_pairs(pack(0x3c03800e,0x8c638000),0x800d8000)),1)

    def test_mirrored_bytes(self):
        self.assertEqual(common_prefix(b'abcdefg',b'abcXYZ'),3)
        self.assertEqual(common_prefix(b'ab',b'abcdef'),2)

if __name__ == '__main__':
    unittest.main()
