"""Synthetic tests for correlating MIPS CFG alternatives with executed PC paths."""
import struct
import unittest
from tools.mips_caller_cfg_sources import inspect

BASE = 0x80010000

def i(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff)

class CFGProbePathTests(unittest.TestCase):
    def look(self, pcs=None):
        words = [i(4,4,6,2),0,i(9,6,4,1),0,i(3),0]
        code = struct.pack('<6I', *words)
        return inspect(code, BASE, BASE+16, 4, observed_pcs=pcs)

    def test_taken_branch_matches_unmodified_incoming_a0(self):
        r = self.look([BASE,BASE+4,BASE+12,BASE+16,BASE+20])
        self.assertTrue(r['synthetic_probe_path_matched'])
        self.assertEqual(r['synthetic_probe_matching_path_count'],1)
        self.assertEqual(r['paths_to_call'],2)
        self.assertEqual(r['synthetic_probe_argument_sources'][0]['incoming_gprs'],[4])
        self.assertEqual(r['arguments'][0]['incoming_gprs'],[4,6])
        self.assertFalse(r['runtime_path_confirmed'])

    def test_not_taken_branch_matches_a2_derived_a0(self):
        r = self.look([BASE,BASE+4,BASE+8,BASE+12,BASE+16,BASE+20])
        self.assertTrue(r['synthetic_probe_path_matched'])
        self.assertEqual(r['synthetic_probe_argument_sources'][0]['incoming_gprs'],[6])

    def test_missing_delay_slot_cannot_be_correlated(self):
        r = self.look([BASE,BASE+12,BASE+16,BASE+20])
        self.assertFalse(r['synthetic_probe_path_matched'])
        self.assertEqual(r['synthetic_probe_argument_sources'],[])

    def test_trace_starting_after_window_does_not_match(self):
        r = self.look([BASE+4,BASE+8,BASE+12,BASE+16,BASE+20])
        self.assertFalse(r['synthetic_probe_window_covered'])
        self.assertFalse(r['synthetic_probe_path_matched'])

    def test_not_supplied_stays_only_static(self):
        r = self.look()
        self.assertFalse(r['synthetic_probe_path_supplied'])
        self.assertFalse(r['synthetic_probe_path_matched'])
        self.assertEqual(r['synthetic_probe_argument_sources'],[])

    def test_extraneous_pc_rejected_without_information_leak(self):
        r = self.look([BASE,BASE+4,BASE+12,BASE+16,BASE+20,BASE+40])
        self.assertFalse(r['synthetic_probe_path_matched'])
        self.assertNotIn(f'{BASE:08X}',str(r))

    def test_invalid_observed_pc_type_raises(self):
        with self.assertRaises(ValueError):
            self.look(['bad'])

if __name__ == '__main__':
    unittest.main()
