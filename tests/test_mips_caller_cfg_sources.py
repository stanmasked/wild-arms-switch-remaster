import struct
import unittest
from tools.mips_caller_cfg_sources import inspect

BASE = 0x80010000

def i(op, rs=0, rt=0, immediate=0):
    return op << 26 | rs << 21 | rt << 16 | (immediate & 0xffff)

def code(words):
    return struct.pack('<%dI' % len(words), *words)

def run(words, lookback=None, **kwargs):
    if lookback is None: lookback = len(words) - 2
    return inspect(code(words), BASE, BASE + 4*lookback, lookback, **kwargs)

class CFGCallerSourcesTests(unittest.TestCase):
    def test_straight_line_matches_stack_origin(self):
        result = run([i(9,29,5,16),0,i(3),0])
        self.assertTrue(result['window_usable'])
        arg = next(x for x in result['arguments'] if x['gpr']==5)
        self.assertEqual(arg['source_kinds'],['stack_pointer_derived'])
        self.assertEqual(arg['incoming_gprs'],[29])
        self.assertTrue(arg['same_origin_across_paths'])
        self.assertEqual(result['paths_to_call'],1)

    def test_branch_with_two_sources_is_not_collapsed(self):
        # BEQ unknown a0,a2: target index 3 or fall-through index 2.
        # One path keeps incoming a0, the other replaces it from a2.
        words=[i(4,4,6,2),0,i(9,6,4,1),0,i(3),0]
        result=run(words)
        self.assertTrue(result['window_usable'])
        self.assertEqual(result['paths_to_call'],2)
        arg=result['arguments'][0]
        self.assertFalse(arg['same_origin_across_paths'])
        self.assertEqual(arg['incoming_gprs'],[4,6])

    def test_known_equal_branch_prunes_unreachable(self):
        words=[i(4,0,0,2),0,i(9,6,4,1),i(9,7,4,2),i(3),0]
        result=run(words)
        self.assertTrue(result['window_usable'])
        self.assertEqual(result['paths_to_call'],1)
        self.assertEqual(result['arguments'][0]['incoming_gprs'],[7])

    def test_beq_same_unknown_gpr_only_takes_branch(self):
        words=[i(4,4,4,2),0,i(9,6,4,1),i(9,7,4,2),i(3),0]
        result=run(words)
        self.assertTrue(result['window_usable'])
        self.assertEqual(result['paths_to_call'],1)
        self.assertEqual(result['arguments'][0]['incoming_gprs'],[7])

    def test_bne_same_unknown_gpr_never_takes_branch(self):
        words=[i(5,4,4,2),0,i(9,6,4,1),0,i(3),0]
        result=run(words)
        self.assertTrue(result['window_usable'])
        self.assertEqual(result['paths_to_call'],1)
        self.assertEqual(result['arguments'][0]['incoming_gprs'],[6])

    def test_delay_slot_executes_on_both_branches(self):
        words=[i(4,4,6,2),i(9,29,5,16),0,i(9,0,10,0),i(3),0]
        result=run(words)
        self.assertTrue(result['window_usable'])
        arg=result['arguments'][1]
        self.assertTrue(arg['same_origin_across_paths'])
        self.assertEqual(arg['incoming_gprs'],[29])

    def test_branch_load_delay_source_is_old_value(self):
        # LW a0,0(a2); immediately BEQ a0,a3 branches using old a0.
        words=[i(35,6,4,0),i(4,4,7,2),0,i(9,7,5,16),i(3),0]
        result=run(words)
        self.assertTrue(result['window_usable'])
        # At call the earlier LW must have retired on both paths.
        self.assertEqual(result['arguments'][0]['source_kinds'],['memory_derived'])

    def test_jal_slot_load_reported_pending(self):
        result=run([i(9,29,5,16),i(3),i(35,6,4,0)])
        self.assertTrue(result['window_usable'])
        self.assertTrue(result['arguments'][0]['load_pending_on_any_path'])

    def test_branch_exits_window_refused(self):
        result=run([i(4,4,6,5),0,i(9,29,5,16),i(3),0])
        self.assertFalse(result['window_usable'])

    def test_backward_branch_refused(self):
        result=run([i(9,29,5,16),i(4,4,6,-2),0,i(3),0])
        self.assertFalse(result['window_usable'])

    def test_branch_in_slot_refused(self):
        result=run([i(4,4,6,2),i(4,0,0,1),0,i(3),0])
        self.assertFalse(result['window_usable'])

    def test_branch_slot_overlaps_jal_refused(self):
        result=run([i(9,29,5,16),i(4,4,6,1),i(3),0])
        self.assertFalse(result['window_usable'])

    def test_static_external_entry_cannot_be_proved(self):
        result=run([i(9,29,5,16),i(3),0])
        self.assertFalse(result['runtime_path_confirmed'])
        self.assertFalse(result['external_entry_edges_ruled_out'])

    def test_path_limit_is_bounded(self):
        words=[i(4,4,6,2),0,i(9,7,4,1),i(9,7,4,2),i(3),0]
        result=run(words, max_paths=1)
        self.assertFalse(result['window_usable'])
        self.assertEqual(result['reason'],'path_limit')

    def test_bgtz_invalid_rt_rejected(self):
        result=run([i(7,4,2,2),0,0,i(3),0])
        self.assertFalse(result['window_usable'])

    def test_regimm_conditional(self):
        result=run([i(1,4,0,2),0,0,i(9,29,5,16),i(3),0])
        self.assertTrue(result['window_usable'])
        self.assertEqual(result['paths_to_call'],2)

    def test_unsupported_cop2_refused(self):
        result=run([18<<26,i(3),0])
        self.assertFalse(result['window_usable'])

if __name__ == '__main__': unittest.main()
