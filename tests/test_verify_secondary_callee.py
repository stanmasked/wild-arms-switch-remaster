import unittest
from tools.verify_secondary_callee import SIGNATURE, verify

class SecondaryCalleeTests(unittest.TestCase):
    def fixture(self):
        base,size=0x80011420,0xC1800
        data=bytearray(2048+size)
        data[:8]=b'PS-X EXE'
        data[0x18:0x1c]=base.to_bytes(4,'little')
        data[0x1c:0x20]=size.to_bytes(4,'little')
        for pc,word in SIGNATURE.items():
            pos=2048+pc-base
            data[pos:pos+4]=word.to_bytes(4,'little')
        return data

    def test_exact(self):
        self.assertEqual(verify(self.fixture())['checked_instructions'],9)
    def test_argument_registers(self):
        r=verify(self.fixture())
        self.assertEqual((r['a0_saved_in'],r['a2_saved_in'],r['a3_saved_in']),('s7','s6','s5'))
    def test_signed_halfword(self):
        self.assertEqual(verify(self.fixture())['halfword_read'],'lh v0,0x52(s7)')
    def test_two_calls(self):
        self.assertEqual(verify(self.fixture())['helper_calls'],['0x800B70E8']*2)
    def test_mutated(self):
        d=self.fixture();d[2048+0x8007772c-0x80011420]^=1
        with self.assertRaises(ValueError):verify(d)
    def test_invalid(self):
        with self.assertRaises(ValueError):verify(b'invalid')

if __name__=='__main__':unittest.main()
