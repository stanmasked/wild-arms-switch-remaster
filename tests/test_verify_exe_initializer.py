import unittest
from tools.verify_exe_initializer import EXPECTED, verify, from_executable

class ExeInitializerTests(unittest.TestCase):
    def test_exact_signature(self):
        r=verify(EXPECTED)
        self.assertEqual(len(r['stores']),9)
        self.assertEqual([x['value'] for x in r['stores']],[0]*6+[4096]*3)

    def test_delay_slot_store(self):
        r=verify(EXPECTED)
        self.assertEqual([x['offset'] for x in r['stores'] if x['delay_slot']],['0x24'])

    def test_store_widths(self):
        self.assertEqual([x['width_bits'] for x in verify(EXPECTED)['stores']],
                         [16,16,16,32,32,32,32,32,32])

    def test_changed_instruction_rejected(self):
        words=list(EXPECTED)
        words[1]=0
        with self.assertRaises(ValueError): verify(words)

    def test_exe_mapping(self):
        base=0x80011420
        data=bytearray(2048+0xc1800)
        data[:8]=b'PS-X EXE'
        data[0x18:0x1c]=base.to_bytes(4,'little')
        data[0x1c:0x20]=(0xc1800).to_bytes(4,'little')
        off=2048+0x8006ce70-base
        for i,w in enumerate(EXPECTED):
            data[off+i*4:off+i*4+4]=w.to_bytes(4,'little')
        self.assertEqual(len(from_executable(data)['stores']),9)

    def test_invalid_exe(self):
        with self.assertRaises(ValueError): from_executable(b'wrong')

if __name__=='__main__': unittest.main()
