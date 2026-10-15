import struct
import unittest
from tools.audit_gp0_opcode_provenance import decode_load, decode_store, trace_packet_first_word

def ins(op,base,reg,off):
    return (op<<26)|(base<<21)|(reg<<16)|(off&65535)

class GP0OpcodeProvenance(unittest.TestCase):
    def test_store_sizes_and_signed_offsets(self):
        self.assertEqual(decode_store(ins(0x2b,11,12,-4))['offset'],-4)
        self.assertEqual(decode_store(ins(0x28,11,1,7))['operation'],'SB')
        self.assertIsNone(decode_store(ins(0x23,11,12,4)))

    def test_lbu_is_not_an_opcode_value(self):
        self.assertEqual(decode_load(ins(0x24,11,1,7))['operation'],'LBU')
        self.assertIsNone(decode_load(ins(0x28,11,1,7)))

    def test_save_restore_opcode_byte(self):
        words=[ins(0x24,11,1,7),ins(0x2b,11,12,4),ins(0x28,11,1,7)]
        events=trace_packet_first_word(struct.pack('<3I',*words),0,0,12,11,lookback=0)
        self.assertEqual(len(events),2)
        self.assertFalse(events[0]['lbu_opcode_byte_preservation'])
        self.assertTrue(events[1]['lbu_opcode_byte_preservation'])

    def test_no_matching_load_is_not_preservation(self):
        words=[ins(0x24,12,1,7),ins(0x28,11,1,7)]
        events=trace_packet_first_word(struct.pack('<2I',*words),0,0,8,11,lookback=0)
        self.assertEqual(len(events),1)
        self.assertFalse(events[0]['lbu_opcode_byte_preservation'])

    def test_non_packet_register_ignored(self):
        words=[ins(0x2b,12,1,4),ins(0x28,12,1,7)]
        self.assertEqual(trace_packet_first_word(struct.pack('<2I',*words),0,0,8,11,lookback=0),[])

    def test_pre_branch_and_delay_slot_distinguished(self):
        words=[ins(0x2b,11,12,4),ins(0x28,11,1,7),ins(0x2b,11,12,4),
               0,ins(0x28,11,1,7)]
        events=trace_packet_first_word(struct.pack('<5I',*words),0,8,20,11)
        self.assertEqual([e['phase'] for e in events],
                         ['before_blez','before_blez','delay_slot','fallthrough'])

if __name__=='__main__': unittest.main()
