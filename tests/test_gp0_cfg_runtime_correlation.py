"""Synthetic end-to-end PS-X EXE CFG path/replay correlation."""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze

BASE = 0x80010000

def i(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff)

def fixture(words):
    header = bytearray(2048)
    header[:8] = b'PS-X EXE'
    struct.pack_into('<II', header, 0x18, BASE, 4 * len(words))
    return bytes(header) + struct.pack('<%dI' % len(words), *words)

def example():
    call = BASE + 32
    builder = BASE + 48
    jal = (3 << 26) | ((builder >> 2) & 0x03ffffff)
    words = [i(4,4,6,2),0,i(9,6,4,1),0,i(9,29,5,16),0,0,0,
             jal,0,0,0,i(41,5,4,0),(31<<21)|8,0]
    return fixture(words),call,builder,builder+4

class CFGReplayCorrelationTests(unittest.TestCase):
    def test_taken_branch_reports_observed_a0_origin(self):
        blob,call,builder,end = example()
        r = analyze(blob,start=builder,end=end,call=call,caller_cfg=True,
                    caller_replay=True,caller_lookback=8,replay_cfg_window=True)
        cfg = r['caller_argument_cfg']
        self.assertTrue(cfg['window_usable'])
        self.assertEqual(cfg['paths_to_call'],2)
        self.assertTrue(cfg['synthetic_probe_path_matched'])
        self.assertTrue(cfg['synthetic_probe_window_covered'])
        self.assertEqual(cfg['synthetic_probe_argument_sources'][0]['incoming_gprs'],[4])
        self.assertTrue(r['exploratory_trace']['returned_to_caller'])
        self.assertFalse(cfg['runtime_path_confirmed'])
        self.assertFalse(cfg['external_entry_edges_ruled_out'])

    def test_not_taken_branch_reports_a2_derived_a0(self):
        blob,call,builder,end = example()
        r = analyze(blob,start=builder,end=end,call=call,caller_cfg=True,
                    caller_replay=True,caller_lookback=8,replay_cfg_window=True,
                    initial_registers={4:1,6:0})
        cfg = r['caller_argument_cfg']
        self.assertTrue(cfg['synthetic_probe_path_matched'])
        self.assertEqual(cfg['synthetic_probe_argument_sources'][0]['incoming_gprs'],[6])
        self.assertTrue(r['exploratory_trace']['returned_to_caller'])

    def test_default_replay_cannot_claim_coverage_of_longer_window(self):
        blob,call,builder,end = example()
        r = analyze(blob,start=builder,end=end,call=call,caller_cfg=True,
                    caller_replay=True,caller_lookback=8)
        cfg = r['caller_argument_cfg']
        self.assertFalse(cfg['synthetic_probe_window_covered'])
        self.assertFalse(cfg['synthetic_probe_path_matched'])
        self.assertEqual(cfg['synthetic_probe_argument_sources'],[])

    def test_default_four_word_window_correlates_without_new_flag(self):
        blob,call,builder,end = example()
        r = analyze(blob,start=builder,end=end,call=call,caller_cfg=True,
                    caller_replay=True)
        cfg = r['caller_argument_cfg']
        self.assertTrue(cfg['synthetic_probe_window_covered'])
        self.assertTrue(cfg['synthetic_probe_path_matched'])
        self.assertEqual(cfg['paths_to_call'],1)

    def test_static_only_keeps_probe_unobserved(self):
        blob,call,builder,end = example()
        r = analyze(blob,start=builder,end=end,call=call,caller_cfg=True,
                    caller_lookback=8)
        self.assertFalse(r['caller_argument_cfg']['synthetic_probe_path_supplied'])
        self.assertFalse(r['caller_argument_cfg']['synthetic_probe_path_matched'])

    def test_invalid_mode_combination_fails_closed(self):
        blob,call,builder,end = example()
        with self.assertRaises(ValueError):
            analyze(blob,start=builder,end=end,call=call,replay_cfg_window=True)
        with self.assertRaises(ValueError):
            analyze(blob,start=builder,end=end,call=call,caller_replay=True,
                    caller_cfg=True,caller_lookback=3,replay_cfg_window=True)

    def test_invalid_cfg_path_cannot_be_replayed(self):
        blob,call,builder,end = example()
        bad = bytearray(blob)
        struct.pack_into('<I',bad,2048+4,18<<26)
        with self.assertRaisesRegex(ValueError,'invalid caller CFG'):
            analyze(bytes(bad),start=builder,end=end,call=call,
                    caller_cfg=True,caller_replay=True,
                    caller_lookback=8,replay_cfg_window=True)

if __name__ == '__main__':
    unittest.main()
