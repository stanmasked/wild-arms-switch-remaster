import math
import struct
import unittest
from tools.audit_gp0_trig_table import analyze, indexed_lookup, signed16

BASE=0x80010000
TABLE=BASE+0x100
PC=BASE+0x28

def lookup_words(table):
    hi=(table+0x8000)>>16
    off=table-(hi<<16)
    return (15<<26 | 25<<16 | (hi&65535),
            25<<21 | 24<<16 | 25<<11 | 33,
            35<<26 | 25<<21 | 25<<16 | (off&65535))

def fixture(entries=16):
    data=bytearray(0x200)
    struct.pack_into('<3I',data,PC-BASE-8,*lookup_words(TABLE))
    for i in range(entries):
        t=2*math.pi*i/entries
        struct.pack_into('<hh',data,TABLE-BASE+i*4,
                         round(4096*math.sin(t)),round(4096*math.cos(t)))
    return data

class TrigTableTests(unittest.TestCase):
    def test_signed_halfword(self):self.assertEqual(signed16(0xf000),-4096)
    def test_full_indexed_lookup(self):self.assertTrue(indexed_lookup(fixture(),BASE,PC,TABLE))
    def test_wrong_base_register(self):
        b=fixture();w=struct.unpack_from('<I',b,PC-BASE)[0];struct.pack_into('<I',b,PC-BASE,(w & ~(31<<21)) | 20<<21)
        self.assertFalse(indexed_lookup(b,BASE,PC,TABLE))
    def test_wrong_address(self):self.assertFalse(indexed_lookup(fixture(),BASE,PC,TABLE+4))
    def test_wrong_add_opcode(self):
        b=fixture();w=struct.unpack_from('<I',b,PC-BASE-4)[0];struct.pack_into('<I',b,PC-BASE-4,(w&~63)|35)
        self.assertFalse(indexed_lookup(b,BASE,PC,TABLE))
    def test_outside_image(self):self.assertFalse(indexed_lookup(b'',BASE,PC,TABLE))
    def test_synthetic_trig_table(self):
        r=analyze(fixture(),BASE,TABLE,16,(PC,))
        self.assertTrue(r['cardinal_points_match'])
        self.assertEqual(r['max_abs_error_against_rounded_trig'],0)
        self.assertEqual(r['complete_lookup_chain_count'],1)
        self.assertFalse(r['values_emitted'])
    def test_corrupted_cardinal_point(self):
        b=fixture();struct.pack_into('<h',b,TABLE-BASE,100)
        self.assertFalse(analyze(b,BASE,TABLE,16,(PC,))['cardinal_points_match'])
    def test_not_enough_table_bytes(self):
        self.assertFalse(analyze(b'',BASE,TABLE,16,(PC,))['table_in_image'])
    def test_reject_wrong_entry_count(self):
        with self.assertRaises(ValueError):analyze(fixture(),BASE,TABLE,3,(PC,))

if __name__=='__main__':unittest.main()
