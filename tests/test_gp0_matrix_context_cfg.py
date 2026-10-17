import struct
import unittest
from tools.audit_gp0_matrix_context_cfg import trace

BASE=0x80010000
START=BASE+0x20

def run(words):
    image=bytes(0x20)+struct.pack('<%dI'%len(words),*words)
    return trace(image,BASE,START,START+4*(len(words)-1))
def j(addr): return 2<<26 | ((addr>>2)&0x3ffffff)
def beq(off): return 4<<26 | 8<<21 | 9<<16 | (off&65535)

class ContextTests(unittest.TestCase):
    def test_delay_context_is_separate(self):
        # The branch lands at its own slot, now entered normally.
        r=run([beq(0),0,0])
        edges={(e['from'],e['to']) for e in r['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
        self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',f'0x{START+4:08X}'),edges)
    def test_mixed_context_edges_are_stable_and_keep_both_entries(self):
        # A branch to its own delay slot creates two *distinct* nodes at
        # the same PC. Sorting must never compare None and an integer.
        first=run([beq(0),0,0])
        second=run([beq(0),0,0])
        self.assertEqual(first['edges'],second['edges'])
        self.assertEqual([edge['from'] for edge in first['edges']],[
            f'0x{START:08X}',
            f'0x{START+4:08X}',
            f'0x{START+4:08X}@delay_of_0x{START:08X}',
            f'0x{START+4:08X}@delay_of_0x{START:08X}',
        ])
        # Unknown BEQ predicate has both taken and not-taken targets.
        self.assertEqual(len(first['edges']),4)
        self.assertTrue(first['valid_range'])

    def test_unconditional_jump_not_fallthrough(self):
        r=run([j(START+16),0,0,0,0])
        self.assertFalse(any(e['to']==f'0x{START+8:08X}' for e in r['edges']))
    def test_indirect_is_terminal(self):
        r=run([(31<<21)|8,0,0])
        self.assertEqual(r['edges'],[])
        self.assertTrue(r['unresolved'])
    def test_branch_likely_taken_executes_delay_slot(self):
        report=run([20<<26|8<<21|9<<16|2,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
        self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',f'0x{START+12:08X}'),edges)

    def test_branch_likely_not_taken_annuls_slot(self):
        report=run([20<<26|8<<21|9<<16|1,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+8:08X}'),edges)
        self.assertNotIn((f'0x{START:08X}',f'0x{START+4:08X}'),edges)

    def test_branch_likely_annulled_edge_is_not_a_delay_context(self):
        report=run([20<<26|8<<21|9<<16|2,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}', f'0x{START+8:08X}'),edges)
        self.assertIn((f'0x{START:08X}', f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
        self.assertNotIn((f'0x{START:08X}', f'0x{START+4:08X}'),edges)

    def test_regimm_likely_taken_and_annulled_edges(self):
        for subop in (2,3):
            instruction=(1<<26)|(8<<21)|(subop<<16)|2
            report=run([instruction,0,0,0])
            edges={(e['from'],e['to']) for e in report['edges']}
            self.assertIn((f'0x{START:08X}',f'0x{START+8:08X}'),edges)
            self.assertIn((f'0x{START:08X}',f'0x{START+4:08X}@delay_of_0x{START:08X}'),edges)
            self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',f'0x{START+12:08X}'),edges)

    def test_cop2_branch_does_not_make_false_reachable_edges(self):
        bc2=(18<<26)|(8<<21)|(1<<16)|2
        report=run([bc2,0,0,0])
        self.assertEqual(report['edges'],[])
        self.assertTrue(any(x['reason']=='coprocessor_branch_requires_semantics'
                            for x in report['unresolved']))

    def test_beq_same_register_is_always_taken(self):
        branch=(4<<26)|(8<<21)|(8<<16)|2
        report=run([branch,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',
                       f'0x{START+12:08X}'),edges)
        self.assertNotIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',
                          f'0x{START+8:08X}'),edges)

    def test_bnel_same_register_annuls_slot(self):
        branch=(21<<26)|(8<<21)|(8<<16)|2
        report=run([branch,0,0,0])
        self.assertEqual(report['edges'][0],
                         {'from':f'0x{START:08X}','to':f'0x{START+8:08X}'})
        self.assertFalse(any('@delay_of_' in e['to'] for e in report['edges']))

    def test_zero_register_blez_is_taken_after_slot(self):
        branch=(6<<26)|2
        report=run([branch,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',
                       f'0x{START+12:08X}'),edges)
        self.assertNotIn((f'0x{START+4:08X}@delay_of_0x{START:08X}',
                          f'0x{START+8:08X}'),edges)

    def test_zero_register_bgtzl_annuls_slot(self):
        branch=(23<<26)|2
        report=run([branch,0,0,0])
        edges={(e['from'],e['to']) for e in report['edges']}
        self.assertIn((f'0x{START:08X}',f'0x{START+8:08X}'),edges)
        self.assertFalse(any('@delay_of_' in edge[1] for edge in edges))

    def test_zero_register_regimm_likely_predicates(self):
        for rt,taken in ((2,False),(3,True)):
            branch=(1<<26)|(rt<<16)|2
            report=run([branch,0,0,0])
            edges={(e['from'],e['to']) for e in report['edges']}
            taken_slot=(f'0x{START:08X}',f'0x{START+4:08X}@delay_of_0x{START:08X}')
            skip_slot=(f'0x{START:08X}',f'0x{START+8:08X}')
            self.assertEqual(taken_slot in edges,taken)
            self.assertEqual(skip_slot in edges,not taken)

    def test_invalid(self):
        self.assertFalse(trace(b'',BASE,START,START)['valid_range'])

if __name__=='__main__':
    unittest.main()
