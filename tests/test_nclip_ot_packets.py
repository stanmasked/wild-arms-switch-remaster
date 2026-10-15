import struct
import unittest
from tools.audit_nclip_ot_packets import audit, recognize

def packet_words(size=9,old=9,packet=11,slot=13,maskreg=1,sizereg=1):
    return [0x4b58002d,
            (35<<26)|(slot<<21)|(old<<16),
            (15<<26)|(maskreg<<16)|255,
            (13<<26)|(maskreg<<21)|(maskreg<<16)|65535,
            (packet<<21)|(maskreg<<16)|(packet<<11)|36,
            (15<<26)|(sizereg<<16)|(size<<8),
            (old<<21)|(sizereg<<16)|(old<<11)|37,
            (43<<26)|(packet<<21)|(old<<16),
            (43<<26)|(slot<<21)|(packet<<16)]

class PacketLinkAudit(unittest.TestCase):
    def test_four_packet_lengths(self):
        for count in (4,6,7,9):
            w=packet_words(count)
            result=recognize(w,list(range(4096,4096+len(w)*4,4)))
            self.assertEqual(result['packet_words'],count)
            self.assertEqual(result['packet_header_store'],'0x0000101C')
            self.assertEqual(result['ot_head_store'],'0x00001020')

    def test_ot_store_must_match_packet(self):
        words=packet_words()
        words[-1]=(43<<26)|(13<<21)|(12<<16)
        self.assertIsNone(recognize(words,list(range(0,len(words)*4,4))))

    def test_length_mask_must_be_exact(self):
        words=packet_words()
        words[3]^=1
        self.assertIsNone(recognize(words,list(range(0,len(words)*4,4))))

    def test_backward_branch_ignored(self):
        words=[0x4b400006,0x4809c000,0x1920fffc,0]+packet_words()
        result=audit(struct.pack('<%dI'%len(words),*words),0x80010000)
        self.assertEqual(result['ot_packet_candidates'],0)

    def test_complete_positive_path(self):
        words=[0x4b400006,0x4809c000,0x1920000d,0,
               0xe96c0008,0xe96d0014,0xe96e0020]+packet_words()+[0]
        result=audit(struct.pack('<%dI'%len(words),*words),0x80010000)
        self.assertEqual(result['ot_packet_candidates'],1)
        self.assertEqual(result['sxy_triplet_count'],1)
        self.assertEqual(result['sites'][0]['ot_packet']['packet_words'],9)

if __name__=='__main__': unittest.main()
