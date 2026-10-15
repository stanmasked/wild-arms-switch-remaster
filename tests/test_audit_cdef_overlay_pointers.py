import unittest
from tools.audit_cdef_overlay_pointers import pointer_entries, compare_mapped

class PointerMappingTests(unittest.TestCase):
    def fixture(self):
        data=bytearray(0x8000)
        for start in (0,0x4000):
            for i in range(12):
                data[start+4*i:start+4*i+4]=(0x8017c100+i*4).to_bytes(4,'little')
                data[start+0x100+i*4:start+0x104+i*4]=(0x27bdff00+i).to_bytes(4,'little')
        return data

    def test_mapped(self):
        r=pointer_entries(self.fixture(),0)
        self.assertEqual(len(r),12)
        self.assertEqual(r[0]['mapped_offset'],'0x100')
        self.assertEqual(r[0]['target_first_word'],'0x27bdff00')

    def test_identical_regions(self):
        r=compare_mapped(self.fixture(),0,0x4000)
        self.assertTrue(r['same_pointer_words'])
        self.assertTrue(r['same_target_words'])
        self.assertEqual(r['mapped_count'],12)

    def test_difference_detected(self):
        data=self.fixture()
        data[0x4100] ^= 0xff
        self.assertFalse(compare_mapped(data,0,0x4000)['same_target_words'])

    def test_unmapped(self):
        data=bytearray(128)
        data[:4]=(0x80000100).to_bytes(4,'little')
        self.assertIsNone(pointer_entries(data,0,count=1)[0]['mapped_offset'])

    def test_invalid_start(self):
        with self.assertRaises(ValueError):
            pointer_entries(b'abc',-1)

if __name__=='__main__':
    unittest.main()
