import struct
import unittest
from tools.audit_gp0_packet_field16 import instruction, pointer_field_stores, audit


def lw(dst, src, offset):
    return (35<<26)|(src<<21)|(dst<<16)|(offset&65535)

def sw(src, base, offset):
    return (43<<26)|(base<<21)|(src<<16)|(offset&65535)

def addu(dst, lhs, rhs):
    return (lhs<<21)|(rhs<<16)|(dst<<11)|33

def build(cursor_offset=0, base_reg=17):
    return [lw(3,base_reg,12),lw(5,3,cursor_offset),
            lw(2,base_reg,0),addu(2,2,5),sw(2,base_reg,16)]

class Gp0PacketField16Tests(unittest.TestCase):
    def scan(self, words):
        return pointer_field_stores(struct.pack(f'<{len(words)}I',*words),0x80010000)

    def test_decoder(self):
        self.assertEqual(instruction(lw(3,17,12)),('LW',17,3,12))
        self.assertEqual(instruction(sw(2,17,16)),('SW',17,2,16))
        self.assertEqual(instruction(addu(2,2,5)),('ADDU',2,5,2))

    def test_two_offset_word_layouts(self):
        for offset in (0,4):
            with self.subTest(offset=offset):
                matches=self.scan(build(offset))
                self.assertEqual(len(matches),1)
                self.assertEqual(matches[0]['cursor_word_offset'],offset)
                self.assertEqual(matches[0]['result_field_offset'],16)

    def test_two_structure_base_registers(self):
        for base in (16,17):
            self.assertEqual(self.scan(build(0,base))[0]['structure_register'],base)

    def test_wrong_target_field_rejected(self):
        words=build();words[-1]=sw(2,17,20)
        self.assertEqual(self.scan(words),[])

    def test_wrong_cursor_field_rejected(self):
        words=build();words[0]=lw(3,17,8)
        self.assertEqual(self.scan(words),[])

    def test_unrelated_address_register_rejected(self):
        words=build();words[1]=lw(5,4,0)
        self.assertEqual(self.scan(words),[])

    def test_unrelated_offset_word_rejected(self):
        words=build(8)
        self.assertEqual(self.scan(words),[])

    def test_add_vs_addu_rejected(self):
        words=build();words[3]=(words[3]&~63)|32
        self.assertEqual(self.scan(words),[])

    def test_empty_image(self):
        self.assertEqual(audit(b'',0)['pattern_matches'],0)
        self.assertFalse(audit(b'',0)['runtime_address_or_packet_contents_recovered'])

if __name__=='__main__':unittest.main()
