"""Synthetic PS-X EXE fixtures; no copyrighted game data."""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze, instruction_family

BASE = 0x80010000

def ins(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)

def fixture(words):
    code = struct.pack('<%dI' % len(words), *words)
    header = bytearray(2048)
    header[:8] = b'PS-X EXE'
    struct.pack_into('<II', header, 0x18, BASE, len(code))
    return bytes(header) + code

class ReplayPreflightTests(unittest.TestCase):
    def test_family_categories(self):
        self.assertEqual(instruction_family(ins(18)), ('coprocessor', False))
        self.assertEqual(instruction_family(ins(35)), ('aligned_load', True))
        self.assertEqual(instruction_family(ins(41)), ('aligned_store', True))

    def test_static_scan_does_not_emit_words(self):
        r = analyze(fixture([ins(9,0,9,4096), ins(41,5,9,0), 0, 0]),
                    start=BASE, end=BASE+12)
        self.assertEqual(r['instruction_count'], 4)
        self.assertEqual(r['static_supported_count'], 4)
        self.assertNotIn('exploratory_trace', r)
        self.assertFalse(r['assets_emitted'])

    def test_trace_writes_synthetic_first_matrix_slot(self):
        r = analyze(fixture([ins(9,0,9,4096), ins(41,5,9,0), 0, 0]),
                    start=BASE, end=BASE+12, explore=True)
        t = r['exploratory_trace']
        self.assertTrue(t['reached_return_site'])
        self.assertEqual(t['executed_instructions'], 3)
        self.assertEqual(t['matrix_slot_store_count'], 1)
        self.assertFalse(t['all_matrix_slots_written'])
        self.assertNotIn('gpr', t)
        self.assertNotIn('coefficients', t)

    def test_cop2_stops_before_execution(self):
        r = analyze(fixture([ins(18),0]), start=BASE, end=BASE+4, explore=True)
        self.assertEqual(r['unsupported_families'], {'coprocessor': 1})
        self.assertEqual(r['exploratory_trace']['reason'], 'ValueError')
        self.assertEqual(r['exploratory_trace']['executed_instructions'], 0)

    def test_reject_invalid_range_and_image(self):
        blob = fixture([0,0])
        self.assertFalse(analyze(blob, start=BASE, end=BASE+100)['valid_range'])
        with self.assertRaises(ValueError):
            analyze(b'not an exe', start=BASE, end=BASE+4)

    def test_exploration_rejects_invalid_registers_and_overlap(self):
        blob = fixture([0,0])
        with self.assertRaises(ValueError):
            analyze(blob, start=BASE, end=BASE+4, explore=True,
                    initial_registers={32:0})
        with self.assertRaises(ValueError):
            analyze(blob, start=BASE, end=BASE+4, explore=True,
                    matrix_address=BASE)

    def test_synthetic_stack_prologue_and_matrix_write(self):
        # ADDIU sp,-16; SW t1,12(sp); LW t2,12(sp); NOP; SH t2,0(a1)
        words = [ins(9,29,29,-16), ins(43,29,9,12), ins(35,29,10,12),
                 0, ins(41,5,10,0), 0]
        r = analyze(fixture(words), start=BASE, end=BASE+20,
                    explore=True, initial_registers={9:0x12345678})
        tr = r['exploratory_trace']
        self.assertTrue(tr['reached_return_site'])
        self.assertTrue(tr['synthetic_stack_mapped'])
        self.assertEqual(tr['distinct_matrix_slots_written'], 1)
        self.assertEqual(tr['matrix_slot_store_count'], 1)
        self.assertEqual(tr['executed_instruction_families']['aligned_store'], 2)
        self.assertFalse(tr['return_instruction_executed'])
        self.assertNotIn('gpr', tr)

    def test_dynamic_halt_family_for_unsupported_cop(self):
        tr = analyze(fixture([ins(18),0]), start=BASE,
                     end=BASE+4, explore=True)['exploratory_trace']
        self.assertEqual(tr['halt_instruction_family'], 'coprocessor')
        self.assertEqual(tr['halt_category'], 'unsupported_instruction')

    def test_supported_load_can_fail_from_unmapped_memory(self):
        tr = analyze(fixture([ins(35,8,9,0),0]), start=BASE,
                     end=BASE+4, explore=True)['exploratory_trace']
        self.assertEqual(tr['halt_instruction_family'], 'aligned_load')
        self.assertEqual(tr['halt_category'], 'memory_access_or_alignment')

    def test_trace_bounded_loop(self):
        jump_to_self = (2<<26) | ((BASE>>2)&0x03ffffff)
        r = analyze(fixture([jump_to_self,0,0]), start=BASE, end=BASE+8,
                    explore=True, max_steps=5)
        self.assertEqual(r['exploratory_trace']['reason'], 'step_limit')
        self.assertEqual(r['exploratory_trace']['executed_instructions'], 5)

if __name__ == '__main__':
    unittest.main()
