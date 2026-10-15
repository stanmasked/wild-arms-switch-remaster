import unittest
from tools.audit_record_field54_origin import CHECK, verify

class Field54OriginTests(unittest.TestCase):
    def fixture(self):
        base,size=0x80011420,0xc1800
        exe=bytearray(2048+size)
        exe[:8]=b'PS-X EXE'
        exe[0x18:0x1c]=base.to_bytes(4,'little')
        exe[0x1c:0x20]=size.to_bytes(4,'little')
        for pc,word in CHECK.items():
            off=2048+pc-base
            exe[off:off+4]=word.to_bytes(4,'little')
        return exe
    def test_signature(self):
        self.assertEqual(verify(self.fixture())['checked_words'],8)
    def test_global(self):
        self.assertEqual(verify(self.fixture())['global_source'],'0x800D2CEC')
    def test_stride_factor(self):
        self.assertIn('24*a0',verify(self.fixture())['stored_expression'])
    def test_mutation(self):
        exe=self.fixture()
        exe[2048+0x80078e4c-0x80011420]^=1
        with self.assertRaises(ValueError):
            verify(exe)
    def test_invalid_header(self):
        with self.assertRaises(ValueError):
            verify(b'bad')
    def test_truncated(self):
        with self.assertRaises(ValueError):
            verify(self.fixture()[:4096])

if __name__=='__main__':
    unittest.main()
