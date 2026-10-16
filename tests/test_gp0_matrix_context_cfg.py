import struct
import unittest
from tools.audit_gp0_matrix_context_cfg import trace

BASE=0x80010000
START=BASE+0x20

def run(words):
    image=bytes(0x20)+struct.pack('<%dI'%len(words),*words)
    return trace(image,BASE,START,START+4*(len(words)-1))
def j(addr): return 2<<26 | ((addr>>2)&0x3ffffff)
def beq(off): return 4<<26 | (off&65535)

class ContextTests(unittest.TestCase):
    def test_delay_context_is_separate(self):
        # The branch lands at its own slot, now entered normally.
        r=run([beq(0),0,0])
        edges={(e['from'],e['to']) for e in r['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
        self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',f'0x{START+4:08X}'),edges)
    def test_unconditional_jump_not_fallthrough(self):
        r=run([j(START+16),0,0,0,0])
        self.assertFalse(any(e['to']==f'0x{START+8:08X}' for e in r['edges']))
    def test_indirect_is_terminal(self):
        r=run([(31<<21)|8,0,0])
        self.assertEqual(r['edges'],[])
        self.assertTrue(r['unresolved'])
    def test_branch_likely_taken_executes_delay_slot(self):
        report=run([20<<26|2,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
        self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',f'0x{START+12:08X}'),edges)

    def test_branch_likely_not_taken_annuls_slot(self):
        report=run([20<<26|1,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+8:08X}'),edges)
        self.assertNotIn((f'0x{START:08X}',f'0x{START+4:08X}'),edges)

    def test_branch_likely_annulled_edge_is_not_a_delay_context(self):
        report=run([20<<26|2,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}', f'0x{START+8:08X}'),edges)
        self.assertIn((f'0x{START:08X}', f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
        self.assertNotIn((f'0x{START:08X}', f'0x{START+4:08X}'),edges)

    def test_invalid(self):
        self.assertFalse(trace(b'',BASE,START,START)['valid_range'])

if __name__=='__main__':
    unittest.main()
