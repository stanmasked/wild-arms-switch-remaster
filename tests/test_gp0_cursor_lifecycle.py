import struct
import unittest
from tools.audit_gp0_cursor_lifecycle import decode, lifecycle


def lw(dest, base, offset):
    return (35<<26)|(base<<21)|(dest<<16)|(offset&65535)

def addiu(dest, source, imm, opcode=9):
    return (opcode<<26)|(source<<21)|(dest<<16)|(imm&65535)

def sw(source, base, offset):
    return (43<<26)|(base<<21)|(source<<16)|(offset&65535)


def scan(words, **kwargs):
    return lifecycle(struct.pack(f'<{len(words)}I',*words), 0x80010000, **kwargs)


class CursorLifecycleTests(unittest.TestCase):
    def test_decoder(self):
        self.assertEqual(decode(lw(3,17,0)),('LW',3,17,0))
        self.assertEqual(decode(addiu(2,3,12)),('ADDIU',2,3,12))
        self.assertEqual(decode(sw(2,17,12)),('SW',2,17,12))

    def test_initialization_both_structure_registers(self):
        for base in (16,17):
            found=scan([lw(3,base,0),0,addiu(2,3,12),sw(2,base,12)])
            self.assertEqual(len(found),1)
            self.assertEqual(found[0]['kind'],'initialize_base_plus_12')
            self.assertEqual(found[0]['structure_register'],base)

    def test_cursor_advance(self):
        found=scan([lw(2,16,12),0,addiu(2,2,4),sw(2,16,12)])
        self.assertEqual([m['kind'] for m in found],['advance_cursor_plus_4'])

    def test_addi_variant(self):
        found=scan([lw(3,17,0),addiu(2,3,12,opcode=8),sw(2,17,12)])
        self.assertEqual(len(found),1)

    def test_other_field_is_not_cursor(self):
        self.assertEqual(scan([lw(3,17,0),addiu(2,3,12),sw(2,17,16)]),[])

    def test_wrong_base_register(self):
        self.assertEqual(scan([lw(3,16,0),addiu(2,3,12),sw(2,17,12)]),[])

    def test_other_offsets_not_mistaken_for_initialization(self):
        for offset in (0,4,8,16,-4):
            self.assertEqual(scan([lw(3,16,0),addiu(2,3,offset),sw(2,16,12)]),[])

    def test_other_offsets_not_mistaken_for_advance(self):
        for offset in (0,8,12):
            self.assertEqual(scan([lw(2,16,12),addiu(2,2,offset),sw(2,16,12)]),[])

    def test_range_exclusion_and_validation(self):
        words=[lw(3,17,0),addiu(2,3,12),sw(2,17,12)]
        self.assertEqual(scan(words,region_start=0x8001000c),[])
        with self.assertRaises(ValueError): scan(words,region_stop=0x80010003)

    def test_empty_and_truncated_images(self):
        self.assertEqual(lifecycle(b'',0),[])
        with self.assertRaises(ValueError):lifecycle(b'123',0)

if __name__=='__main__':unittest.main()
