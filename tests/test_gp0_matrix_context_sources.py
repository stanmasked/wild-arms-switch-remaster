import struct
import unittest
from tools.audit_gp0_matrix_context_sources import analyze

BASE=0x80010000
START=BASE+0x20

def lw(rt): return 35<<26 | 25<<21 | rt<<16
def sh(rt,off): return 41<<26 | 5<<21 | rt<<16 | off
def beq(off): return 4<<26 | (off&65535)
def j(target): return 2<<26 | ((target>>2)&0x3ffffff)
def mult(rs,rt): return rs<<21 | rt<<16 | 24
def mflo(rd): return rd<<11 | 18
def fixture(words,loads=()):
    image=bytes(0x20)+struct.pack('<%dI'%len(words),*words)
    return analyze(image,BASE,START,START+4*(len(words)-1),
                   tuple(START+4*i for i in loads))

class ContextSourcesTests(unittest.TestCase):
    def test_hi_lo_through_branch(self):
        r=fixture([lw(8),beq(2),mult(8,9),mflo(10),sh(10,0)],(0,))
        self.assertEqual(r['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START:08X}'])
    def test_normal_and_delay_entry_are_separate(self):
        r=fixture([beq(0),lw(8),sh(8,0)],(1,))
        self.assertTrue(any('@delay_of_' in s['context'] for s in r['candidate_stores']) is False)
        self.assertEqual(r['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START+4:08X}'])
    def test_unsupported_call_blocks_source(self):
        r=fixture([lw(8),3<<26,0,sh(8,0)],(0,))
        self.assertEqual(r['candidate_stores'],[])
        self.assertTrue(r['unresolved_transfers'])
    def test_same_store_has_distinct_delay_and_normal_contexts(self):
        r=fixture([beq(0),sh(8,0),sh(8,2)])
        labels={store['context'] for store in r['candidate_stores'] if store['offset']==0}
        self.assertEqual(labels,{
            f'0x{START+4:08X}',
            f'0x{START+4:08X}@delay_of_0x{START:08X}'
        })

    def test_branch_source_merge_preserves_both_candidates(self):
        # A delayed conditional branches to index 5 or falls through to 2;
        # a direct J in the fallthrough leg rejoins at index 7.
        r=fixture([beq(4),0,lw(8),j(START+28),0,lw(8),0,sh(8,0)],(2,5))
        self.assertEqual(r['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START+8:08X}',f'0x{START+20:08X}'])

    def test_invalid_range(self):
        self.assertFalse(analyze(b'',BASE,START,START)['valid_range'])

if __name__=='__main__':
    unittest.main()
