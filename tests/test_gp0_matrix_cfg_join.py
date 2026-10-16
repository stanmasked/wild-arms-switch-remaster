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
    def test_mult_mflo_provenance(self):
        mult=(8<<21)|(9<<16)|24
        mflo=(10<<11)|18
        result=check([lw(8),mult,mflo,sh(10,0)],(0,))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START:08X}'])
        self.assertTrue(result['hi_lo_tracking'])
    def test_mult_mfhi_provenance(self):
        multu=(8<<21)|(9<<16)|25
        mfhi=(10<<11)|16
        result=check([lw(8),multu,mfhi,sh(10,2)],(0,))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START:08X}'])
    def test_new_product_overwrites_old_lo(self):
        mult1=(8<<21)|(9<<16)|24
        mult2=(10<<21)|(11<<16)|24
        mflo=(12<<11)|18
        result=check([lw(8),mult1,mult2,mflo,sh(12,0)],(0,))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[])
    def test_mtlo_source_to_mflo(self):
        mtlo=(8<<21)|19
        mflo=(10<<11)|18
        result=check([lw(8),mtlo,mflo,sh(10,0)],(0,))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START:08X}'])
    def test_cop2_register_reads_kill_old_gpr_sources(self):
        for cop_rs in (0,2):
            # MFC2/CFC2 write $t0; prior trigonometric lookup is no
            # longer a proven source of the stored register.
            cop_read=(18<<26)|(cop_rs<<21)|(8<<16)
            result=check([lw(8),cop_read,sh(8,0)],(0,))
            self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[])

    def test_cop2_register_writes_do_not_kill_source(self):
        # MTC2/CTC2 transfer GPR into coprocessor and do not change $t0.
        for cop_rs in (4,6):
            cop_write=(18<<26)|(cop_rs<<21)|(8<<16)
            result=check([lw(8),cop_write,sh(8,0)],(0,))
            self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],
                             [f'0x{START:08X}'])

    def test_loop_overwrite_does_not_preserve_stale_lookup(self):
        # Every route to the store passes through the second LW.
        result=check([lw(8),beq(1),0,lw(8),sh(8,0),
                      beq(-4),0,0],(0,3))
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],
                         [f'0x{START+12:08X}'])

    def test_invalid_range(self):
        self.assertFalse(analyze(b'',BASE,START,START)['valid_range'])

if __name__=='__main__':
    unittest.main()
