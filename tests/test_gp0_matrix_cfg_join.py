import struct
import unittest
from tools.audit_gp0_matrix_cfg_join import analyze

BASE=0x80010000
START=BASE+0x20

def lw(rt): return 35<<26|25<<21|rt<<16
def sh(rt,off): return 41<<26|5<<21|rt<<16|off
def beq(off): return 4<<26|(off&65535)
def j(pc): return 2<<26|((pc>>2)&0x3ffffff)
def addiu(rt,rs=0): return 9<<26|rs<<21|rt<<16

def check(words,loads=()):
    b=bytes(0x20)+struct.pack('<%dI'%len(words),*words)
    return analyze(b,BASE,START,START+4*(len(words)-1),
                   tuple(START+4*i for i in loads))

class CFGJoinTests(unittest.TestCase):
    def test_branch_merges_two_lookup_sources(self):
        # Branch goes to 5 or falls through to 2; both reach store at 7.
        result=check([beq(4),0,lw(8),j(START+28),0,lw(8),0,sh(8,0)],(2,5))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START+8:08X}',f'0x{START+20:08X}'])
    def test_overwrite_kills_previous_source(self):
        result=check([lw(8),addiu(8),sh(8,0)],(0,))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[])
    def test_unreachable_store_excluded(self):
        result=check([j(START+16),0,sh(8,0),0,sh(8,2)])
        self.assertEqual([s['offset'] for s in result['candidate_stores']],[2])
    def test_unresolved_indirect_terminates_path(self):
        result=check([lw(8),(31<<21)|8,0,sh(8,0)],(0,))
        self.assertEqual(result['candidate_stores'],[])
        self.assertTrue(result['unresolved_transfers'])
    def test_invalid_range(self):
        self.assertFalse(analyze(b'',BASE,START,START)['valid_range'])

if __name__=='__main__':
    unittest.main()
