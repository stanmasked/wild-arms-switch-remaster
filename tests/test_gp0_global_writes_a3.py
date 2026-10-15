import struct
import unittest
from tools.audit_gp0_global_writes_a3 import (
    direct_global_stores,delay_slot_a3_sources,audit)

def data(*words): return struct.pack(f'<{len(words)}I',*words)
def lui(r,u):return 15<<26|r<<16|(u&65535)
def sw(r,base,off):return 43<<26|base<<21|r<<16|(off&65535)
def addiu(r,base,off):return 9<<26|base<<21|r<<16|(off&65535)
def addu(r,src):return src<<21|r<<11|33
def jal(target):return 3<<26|((target>>2)&0x3ffffff)

class GlobalWriterAndDelaySlot(unittest.TestCase):
    def test_first_global_store(self):
        found=direct_global_stores(data(lui(2,0x800d),sw(4,2,0x2c3c)),0x80010000)
        self.assertEqual(found[0]['global_address'],'0x800D2C3C')
        self.assertEqual(found[0]['source_register'],4)

    def test_second_global_store(self):
        found=direct_global_stores(data(lui(3,0x800d),sw(5,3,0x2db8)),0)
        self.assertEqual(found[0]['global_address'],'0x800D2DB8')

    def test_negative_immediate(self):
        found=direct_global_stores(data(lui(3,0x800e),sw(5,3,-4)),0,targets=(0x800dfffc,))
        self.assertEqual(found[0]['global_address'],'0x800DFFFC')

    def test_wrong_base_must_not_match(self):
        self.assertEqual(direct_global_stores(data(lui(2,0x800d),sw(4,3,0x2c3c)),0),[])

    def test_load_is_not_store(self):
        self.assertEqual(direct_global_stores(data(lui(2,0x800d),35<<26|2<<21|4<<16|0x2c3c),0),[])

    def test_delay_slot_a3_copy(self):
        words=[addiu(16,29,32),jal(0x80077d08),addu(7,16)]
        result=delay_slot_a3_sources(data(*words),0x80010000)
        self.assertEqual(result[0]['a3_source_register'],16)
        self.assertEqual(result[0]['source_from_sp']['signed_offset'],32)

    def test_delay_slot_not_earlier_register_definition(self):
        words=[addiu(16,29,32),addu(7,16),jal(0x80077d08),0]
        self.assertIsNone(delay_slot_a3_sources(data(*words),0x80010000)[0]['a3_source_register'])

    def test_other_jal_ignored(self):
        self.assertEqual(delay_slot_a3_sources(data(jal(0x80070000),addu(7,16)),0x80010000),[])

    def test_indirect_global_writes_not_claimed(self):
        self.assertTrue(audit(b'',0)['indirect_global_writes_excluded'])
        self.assertFalse(audit(b'',0)['runtime_pointer_values_known'])

    def test_unresolved_stack_provenance(self):
        result=delay_slot_a3_sources(data(jal(0x80077d08),addu(7,16)),0x80010000)
        self.assertIsNone(result[0]['source_from_sp'])

if __name__=='__main__':unittest.main()
