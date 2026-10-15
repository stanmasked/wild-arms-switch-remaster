import struct
import unittest
from tools.audit_gp0_matrix_provenance import trace

BASE=0x80010000
START=BASE+0x20

def lw(rt): return 35<<26 | 25<<21 | rt<<16
def sra(rd,rt,sa): return rt<<16 | rd<<11 | sa<<6 | 3
def sh(rt,off): return 41<<26 | 5<<21 | rt<<16 | off
def mult(rs,rt): return rs<<21 | rt<<16 | 24
def mflo(rd): return rd<<11 | 18
def beq(): return 4<<26

def check(seq, loads=(0,)):
    image=b'\0'*0x20+struct.pack('<%dI'%len(seq),*seq)
    pcs=tuple(START+i*4 for i in loads)
    return trace(image,BASE,START,START+4*(len(seq)-1),pcs)

class ProvenanceTests(unittest.TestCase):
    def test_shift_chain(self):
        result=check([lw(8),sra(9,8,12),sh(9,0)])
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[f'0x{START:08X}'])
    def test_mult_mflo(self):
        result=check([lw(8),mult(8,9),mflo(10),sh(10,2)])
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[f'0x{START:08X}'])
    def test_overwrite_kills_source(self):
        result=check([lw(8),35<<26|4<<21|8<<16,sh(8,0)])
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[])
    def test_branch_delay_resets_provenance(self):
        result=check([lw(8),beq(),0,sh(8,0)])
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[])
    def test_store_in_delay_slot_retains_source(self):
        result=check([lw(8),beq(),sh(8,0),sh(8,2)])
        self.assertEqual(result['candidate_stores'][0]['candidate_lookup_sources'],[f'0x{START:08X}'])
        self.assertEqual(result['candidate_stores'][1]['candidate_lookup_sources'],[])
    def test_invalid_image(self):
        self.assertFalse(trace(b'',BASE,START,START)['valid_range'])

if __name__=='__main__':
    unittest.main()
