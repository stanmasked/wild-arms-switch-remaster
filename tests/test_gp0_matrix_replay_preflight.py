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

    def test_synthetic_caller_linkage_is_verified_from_instructions(self):
        # ADDIU a1,sp,16 at call-16 followed by JAL to the constructor.
        caller = BASE + 16
        target = BASE
        jal = (3<<26) | ((target>>2)&0x3ffffff)
        words = [ins(9,29,5,16),0,0,0,jal,0]
        report = analyze(fixture(words), start=BASE, end=BASE+20,
                         call=caller)
        self.assertTrue(report['caller_linkage']['linkage_confirmed'])
        self.assertTrue(report['caller_linkage']['jal_targets_builder'])
        self.assertTrue(report['caller_linkage']['a1_is_sp_plus_16'])

    def test_wrong_caller_linkage_is_not_confirmed(self):
        caller = BASE + 16
        jal_elsewhere = (3<<26) | (((BASE+4)>>2)&0x3ffffff)
        words = [ins(9,29,5,12),0,0,0,jal_elsewhere,0]
        report = analyze(fixture(words), start=BASE, end=BASE+20,
                         call=caller)
        self.assertFalse(report['caller_linkage']['linkage_confirmed'])
        self.assertFalse(report['caller_linkage']['jal_targets_builder'])
        self.assertFalse(report['caller_linkage']['a1_is_sp_plus_16'])

    def test_caller_absent_from_short_image(self):
        report = analyze(fixture([0,0]), start=BASE, end=BASE+4)
        self.assertFalse(report['caller_linkage']['callsite_in_image'])

    def test_frame_layout_all_nine_matrix_halfwords(self):
        # All SH writes use a1=sp+16, inside mapped scratch stack.
        program = [ins(9,0,9,4096)]
        program.extend(ins(41,5,9,off) for off in range(0,18,2))
        program.append(0)
        report = analyze(fixture(program), start=BASE,
                         end=BASE+4*(len(program)-1),
                         explore=True,frame_layout=True)
        trace = report['exploratory_trace']
        self.assertTrue(trace['reached_return_site'])
        self.assertEqual(trace['frame_layout'],'a1_sp_plus_16')
        self.assertEqual(trace['distinct_matrix_slots_written'],9)
        self.assertTrue(trace['all_matrix_slots_written'])
        self.assertNotIn('gpr',trace)
        self.assertNotIn('matrix_address',trace)

    def test_frame_layout_sp_relative_address_matches_a1(self):
        # Alternate pointer computation ADDIU t0,sp,16 writes same buffer.
        program = [ins(9,0,9,4096),ins(9,29,8,16),ins(41,8,9,0),0]
        report = analyze(fixture(program), start=BASE, end=BASE+12,
                         explore=True,frame_layout=True)
        self.assertEqual(report['exploratory_trace']['distinct_matrix_slots_written'],1)

    def test_frame_layout_rejects_conflicting_initial_registers(self):
        blob=fixture([0,0])
        for register in (5,29):
            with self.assertRaises(ValueError):
                analyze(blob,start=BASE,end=BASE+4,explore=True,
                        frame_layout=True,initial_registers={register:123})

    def test_separate_matrix_layout_is_unchanged(self):
        report=analyze(fixture([ins(9,0,9,4096),ins(41,5,9,0),0]),
                       start=BASE,end=BASE+8,explore=True)
        self.assertEqual(report['exploratory_trace']['frame_layout'],'separate_matrix')
        self.assertEqual(report['exploratory_trace']['distinct_matrix_slots_written'],1)

    def _caller_program(self, builder_body):
        call = BASE + 16
        builder = BASE + 64
        jal = (3 << 26) | ((builder >> 2) & 0x03ffffff)
        words = [ins(9, 29, 5, 16), 0, 0, 0, jal, 0, 0]
        words.extend([0] * (16 - len(words)))
        words.extend(builder_body)
        return fixture(words), call, builder, BASE + 4 * (len(words) - 2)

    def test_caller_jal_executes_builder_nine_stores_and_jr(self):
        # Caller computes a1=sp+16; JAL sets ra=caller+8; JR ra returns.
        body = [ins(9, 0, 9, 4096)]
        body.extend(ins(41, 5, 9, offset) for offset in range(0, 18, 2))
        body.extend([(31 << 21) | 8, 0])
        blob, call, builder, ret = self._caller_program(body)
        tr = analyze(blob, start=builder, end=ret, call=call,
                     caller_replay=True)['exploratory_trace']
        self.assertEqual(tr['replay_origin'], 'caller_before_jal')
        self.assertEqual(tr['frame_layout'], 'a1_sp_plus_16')
        self.assertTrue(tr['caller_jal_executed'])
        self.assertTrue(tr['builder_entry_reached'])
        self.assertTrue(tr['return_instruction_executed'])
        self.assertTrue(tr['returned_to_caller'])
        self.assertTrue(tr['all_matrix_slots_written'])
        self.assertEqual(tr['distinct_matrix_slots_written'], 9)
        self.assertEqual(tr['reason'], 'stop_pc')
        self.assertNotIn('gpr', tr)
        self.assertNotIn('matrix_address', tr)

    def test_caller_probe_rejects_mismatched_jal(self):
        body = [ins(9, 0, 9, 1), (31 << 21) | 8, 0]
        blob, call, builder, ret = self._caller_program(body)
        data = bytearray(blob)
        struct.pack_into('<I', data, 2048 + 16,
                         (3 << 26) | (((builder + 4) >> 2) & 0x03ffffff))
        with self.assertRaisesRegex(ValueError, 'caller instructions'):
            analyze(bytes(data), start=builder, end=ret,
                    call=call, caller_replay=True)

    def test_caller_probe_does_not_claim_return_on_direct_jump(self):
        # A jump to caller+8 is not evidence of JR $ra execution.
        call = BASE + 16
        goto_caller = (2 << 26) | (((call + 8) >> 2) & 0x03ffffff)
        blob, call, builder, ret = self._caller_program([goto_caller, 0, 0])
        tr = analyze(blob, start=builder, end=ret, call=call,
                     caller_replay=True)['exploratory_trace']
        self.assertTrue(tr['caller_jal_executed'])
        self.assertTrue(tr['builder_entry_reached'])
        self.assertFalse(tr['returned_to_caller'])
        self.assertFalse(tr['return_instruction_executed'])

    def test_caller_probe_reports_cop_blocker_without_registers(self):
        blob, call, builder, ret = self._caller_program([18 << 26, 0, 0])
        tr = analyze(blob, start=builder, end=ret, call=call,
                     caller_replay=True)['exploratory_trace']
        self.assertTrue(tr['caller_jal_executed'])
        self.assertTrue(tr['builder_entry_reached'])
        self.assertFalse(tr['returned_to_caller'])
        self.assertEqual(tr['halt_category'], 'unsupported_instruction')
        self.assertEqual(tr['halt_instruction_family'], 'coprocessor')
        self.assertNotIn('gpr', tr)

    def test_jr_requires_successful_delay_slot(self):
        # Executing JR alone is not completion when its delay slot traps.
        body = [(31 << 21) | 8, 18 << 26]
        blob, call, builder, ret = self._caller_program(body)
        tr = analyze(blob, start=builder, end=ret, call=call,
                     caller_replay=True)['exploratory_trace']
        self.assertFalse(tr['return_instruction_executed'])
        self.assertFalse(tr['returned_to_caller'])
        self.assertEqual(tr['halt_category'], 'unsupported_instruction')

    def test_early_jr_is_not_builder_final_return(self):
        # An early JR did not execute the identified final return instruction.
        body = [(31 << 21) | 8, 0, 0, (31 << 21) | 8, 0]
        blob, call, builder, ret = self._caller_program(body)
        tr = analyze(blob, start=builder, end=ret, call=call,
                     caller_replay=True)['exploratory_trace']
        self.assertFalse(tr['return_instruction_executed'])
        self.assertFalse(tr['returned_to_caller'])

    def test_reserved_branch_rt_classification(self):
        self.assertEqual(instruction_family(ins(6, 8, 1, 1)), ('branch', False))
        self.assertEqual(instruction_family(ins(7, 8, 1, 1)), ('branch', False))
        self.assertEqual(instruction_family(ins(6, 8, 0, 1)), ('branch', True))

    def test_caller_probe_reports_external_stack_and_angle_input(self):
        # Synthetic caller sets a1 from sp. Builder reads a0 once, which
        # this shortened code path does not initialize.
        blob, call, builder, ret = self._caller_program([
            ins(9,4,8,1), (31 << 21) | 8, 0])
        report = analyze(blob,start=builder,end=ret,call=call,
                         caller_replay=True)
        trace = report['exploratory_trace']
        self.assertEqual(trace['read_before_first_write_gprs'],[4,29])
        self.assertTrue(trace['returned_to_caller'])

    def test_preflight_only_reports_register_ids_not_values(self):
        program = [ins(9,8,9,7), 0]
        report=analyze(fixture(program),start=BASE,end=BASE+4,
                       explore=True,initial_registers={8:0x12345678})
        self.assertEqual(report['exploratory_trace']['read_before_first_write_gprs'],[8])
        self.assertNotIn('register_values',str(report))

    def test_trace_bounded_loop(self):
        jump_to_self = (2<<26) | ((BASE>>2)&0x03ffffff)
        r = analyze(fixture([jump_to_self,0,0]), start=BASE, end=BASE+8,
                    explore=True, max_steps=5)
        self.assertEqual(r['exploratory_trace']['reason'], 'step_limit')
        self.assertEqual(r['exploratory_trace']['executed_instructions'], 5)

if __name__ == '__main__':
    unittest.main()
