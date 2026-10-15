import unittest
from tools.audit_secondary_array import PATTERNS, inspect_exe

class SecondaryArrayTests(unittest.TestCase):
    def sample(self):
        load,size=0x80011420,0xc1800
        exe=bytearray(2048+size)
        exe[:8]=b'PS-X EXE'
        exe[0x18:0x1c]=load.to_bytes(4,'little')
        exe[0x1c:0x20]=size.to_bytes(4,'little')
        for pc,seq in PATTERNS.items():
            at=2048+pc-load
            for i,w in enumerate(seq):
                exe[at+i*4:at+i*4+4]=w.to_bytes(4,'little')
        return exe
    def test_signature(self):
        self.assertEqual(inspect_exe(self.sample())['verified_instruction_words'],15)
    def test_index_scale(self):
        x=inspect_exe(self.sample())
        self.assertEqual(x['site_80078D1C']['scale'],24)
        self.assertEqual(x['site_80078E34']['scale'],24)
    def test_call_target(self):
        self.assertEqual(inspect_exe(self.sample())['site_80078D1C']['next_call'],'0x800776F0')
    def test_changed_call(self):
        data=self.sample()
        at=2048+0x80078d2c-0x80011420
        data[at]^=1
        with self.assertRaises(ValueError):inspect_exe(data)
    def test_bad_header(self):
        with self.assertRaises(ValueError):inspect_exe(b'invalid')
    def test_truncated(self):
        with self.assertRaises(ValueError):inspect_exe(self.sample()[:4096])

if __name__=='__main__':unittest.main()
