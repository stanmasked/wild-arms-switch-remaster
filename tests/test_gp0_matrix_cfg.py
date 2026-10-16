import struct
import unittest
from tools.audit_gp0_matrix_cfg import analyze, direct_successors

BASE = 0x80010000
START = BASE + 0x20

def check(words):
    data = bytes(0x20) + struct.pack('<%dI' % len(words), *words)
    return analyze(data, BASE, START, START + 4*(len(words)-1))

class CFGTests(unittest.TestCase):
    def test_beq_forward(self):
        kind, targets, delayed = direct_successors(4<<26 | 2, START)
        self.assertEqual((kind, targets, delayed), ('conditional', (START+12, START+8), True))
    def test_negative_branch(self):
        self.assertEqual(direct_successors(5<<26 | 0xffff, START)[1][0], START)
    def test_jump_target(self):
        address = START + 16
        self.assertEqual(direct_successors(2<<26 | (address>>2 & 0x3ffffff), START)[1], (address,))
    def test_delay_edges(self):
        report = check([4<<26 | 1, 0, 0, 0])
        self.assertTrue(any(e['kind']=='delay_slot' for e in report['edges']))
        self.assertTrue(any(e['kind']=='conditional' for e in report['edges']))
    def test_external_call_unresolved(self):
        report = check([3<<26, 0, 0])
        self.assertTrue(any(x['reason']=='call_requires_semantics' for x in report['unresolved']))
    def test_indirect_jump_unresolved(self):
        report = check([(31<<21)|8, 0, 0])
        self.assertTrue(any(x['reason']=='indirect_requires_semantics' for x in report['unresolved']))
    def test_branch_likely_unresolved(self):
        report = check([20<<26, 0, 0])
        self.assertTrue(any(x['reason']=='branch_likely_requires_semantics' for x in report['unresolved']))
    def test_unsupported_regimm_does_not_fallthrough(self):
        # REGIMM rt=2 is BLTZL (branch likely): delay-slot semantics differ.
        report = check([(1<<26)|(2<<16),0,0])
        self.assertTrue(any(x['reason']=='regimm_likely_requires_semantics'
                            for x in report['unresolved']))
        self.assertFalse(any(e['from']==f'0x{START+4:08X}' and
                             e['to']==f'0x{START+8:08X}'
                             for e in report['edges']))
    def test_regimm_link_branch_requires_semantics(self):
        # BGEZAL writes $ra depending on branch semantics.
        report = check([(1<<26)|(17<<16), 0, 0])
        self.assertTrue(any(x['reason']=='unsupported_regimm_requires_semantics'
                            for x in report['unresolved']))
        self.assertFalse(any(e['from']==f'0x{START+4:08X}' and
                             e['to']==f'0x{START+8:08X}'
                             for e in report['edges']))

    def test_control_transfer_in_delay_slot_is_unresolved(self):
        report = check([4<<26|2, 2<<26|((START+16)>>2&0x3ffffff), 0, 0, 0])
        self.assertTrue(any(x['reason']=='control_in_delay_slot_unsupported'
                            for x in report['unresolved']))
        self.assertFalse(any(e['from']==f'0x{START+4:08X}' and
                             e['kind']=='delay_slot'
                             for e in report['edges']))

    def test_malformed_jr_not_treated_as_real_jump(self):
        malformed = (31<<21)|(1<<16)|8
        report = check([malformed,0,0])
        self.assertTrue(any(x['reason']=='malformed_jump_encoding'
                            for x in report['unresolved']))

    def test_branch_likely_delay_slot_not_assumed_executed(self):
        report = check([20<<26 | 1, 0, 0])
        self.assertFalse(any(e['from']==f'0x{START:08X}' and
                             e['to']==f'0x{START+4:08X}'
                             for e in report['edges']))
        self.assertTrue(any(x['reason']=='branch_likely_requires_semantics'
                            for x in report['unresolved']))

    def test_unknown_regimm_slot_not_assumed_executed(self):
        report = check([(1<<26)|(2<<16), 0, 0])
        self.assertFalse(any(e['from']==f'0x{START:08X}' and
                             e['kind']=='delay_slot'
                             for e in report['edges']))

    def test_branch_target_entering_delay_slot_is_unresolved(self):
        # First branch targets index 3, which is the delay slot of index 2.
        report = check([4<<26 | 2, 0, 4<<26 | 2, 0, 0, 0])
        self.assertTrue(any(x['reason']=='target_enters_delay_slot'
                            for x in report['unresolved']))
        self.assertFalse(any(e['from']==f'0x{START+4:08X}' and
                             e['to']==f'0x{START+12:08X}'
                             for e in report['edges']))

    def test_out_of_range(self):
        self.assertFalse(analyze(b'', BASE, START, START)['valid_range'])

if __name__ == '__main__':
    unittest.main()
