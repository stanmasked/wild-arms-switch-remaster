import struct
import unittest
from tools.audit_gp0_root_registers import decode,source_at,audit

def lui(reg,upper):
    return (15<<26)|(reg<<16)|(upper&65535)

def lw(dest,base,imm):
    return (35<<26)|(base<<21)|(dest<<16)|(imm&65535)

def addu(dest,lhs,rhs):
    return (lhs<<21)|(rhs<<16)|(dest<<11)|33

def blob(*words):
    return struct.pack(f'<{len(words)}I',*words)

class RootRegisterTests(unittest.TestCase):
    def test_global_pointer(self):
        image=blob(lui(20,0x800d),lw(20,20,0x2c3c))
        out=source_at(image,0x80010000,0x80010004,20)
        self.assertEqual(out['global_address'],'0x800D2C3C')

    def test_negative_offset_address(self):
        image=blob(lui(22,0x800e),lw(22,22,-4))
        self.assertEqual(source_at(image,0,4,22)['global_address'],'0x800DFFFC')

    def test_copy_incoming_a3(self):
        result=source_at(blob(addu(22,7,0)),0,0,22)
        self.assertEqual((result['kind'],result['register']),('incoming_register_copy',7))

    def test_unknown_register_source(self):
        out=source_at(blob(lw(20,4,0)),0,0,20)
        self.assertEqual(out['kind'],'indirect_load_unresolved')

    def test_wrong_destination_rejected(self):
        self.assertIsNone(source_at(blob(lw(20,4,0)),0,0,22))

    def test_nonmatching_lui_rejected(self):
        image=blob(lui(21,0x800d),lw(20,20,0x2c3c))
        self.assertEqual(source_at(image,0,4,20)['kind'],'indirect_load_unresolved')

    def test_invalid_address_rejected(self):
        with self.assertRaises(ValueError):source_at(b'\0'*8,0,8,20)
        with self.assertRaises(ValueError):source_at(b'\0'*8,0,3,20)

    def test_empty_audit_not_fabricated(self):
        result=audit(b'',0)
        self.assertTrue(all(x['status']=='out_of_image' for x in result['records']))
        self.assertFalse(result['runtime_global_values_recovered'])

if __name__=='__main__':unittest.main()
