"""Synthetic tests for privately claimed MIPS-I load-delay/branch timing."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_mips_load_delay_predicates import (
    SCHEMA, REPORT_SCHEMA, MAX_FILE_BYTES, analyze, main,
)

BASE_PC = 0x80010000
LW_T0_A0 = 0x8c880000
LW_T0_A0_NEXT = 0x8c880004
BEQ_T0_ZERO_TAKEN = 0x11000002
BNE_T0_ZERO = 0x15000002
ADDU_T0_T0_ZERO = 0x01004021


def step(slot, word, **extras):
    return {'pc_u32': f'0x{BASE_PC + slot*4:08x}',
            'word_u32': f'0x{word:08x}', **extras}


def fixture(*, loaded=1, old=0, gap=False, op=BEQ_T0_ZERO_TAKEN,
            taken=True, source='synthetic'):
    initial = {'4': '0x80120000', '8': f'0x{old:08x}'}
    steps = [step(0, LW_T0_A0, load_result_u32=f'0x{loaded:08x}')]
    if gap:
        steps.append(step(1, 0))
        steps.append(step(2, op, claimed_taken=taken))
        steps.append(step(3, 0))
        steps.append(step(5 if taken else 4, 0))
    else:
        steps.append(step(1, op, claimed_taken=taken))
        steps.append(step(2, 0))
        steps.append(step(4 if taken else 3, 0))
    return {'schema': SCHEMA, 'source': source,
            'initial_gprs_u32': initial, 'steps': steps}


class LoadDelayPredicatesTests(unittest.TestCase):
    def test_branch_immediately_after_lw_uses_old_register(self):
        r = analyze(fixture(old=0, loaded=1, taken=True))
        self.assertEqual(r['claimed_lw_results_consumed'], 1)
        self.assertEqual(r['claimed_beq_bne_predicates_checked'], 1)
        self.assertEqual(r['branches_comparing_pre_retirement_loaded_register'], 1)
        self.assertEqual(r['mandatory_nop_delay_slots_checked'], 1)
        self.assertTrue(r['synthetic_or_claimed_trace_self_consistent'])
        self.assertFalse(r['original_ps1_execution_authenticated'])
        self.assertFalse(r['original_ps1_pipeline_cycle_accuracy_verified'])
        self.assertFalse(r['game_record_layout_verified'])
        self.assertFalse(r['nintendo_switch_build_verified'])

    def test_one_intervening_nop_makes_loaded_value_visible(self):
        r = analyze(fixture(old=0, loaded=1, gap=True, taken=False))
        self.assertEqual(r['branches_comparing_pre_retirement_loaded_register'], 0)
        self.assertEqual(r['claimed_beq_bne_predicates_checked'], 1)
        self.assertEqual(r['claimed_instructions_checked'], 5)

    def test_old_register_cannot_be_replaced_early(self):
        with self.assertRaisesRegex(ValueError, 'pre-retirement'):
            analyze(fixture(old=0, loaded=1, taken=False))
        with self.assertRaisesRegex(ValueError, 'pre-retirement'):
            analyze(fixture(old=0, loaded=1, gap=True, taken=True))

    def test_branch_after_load_with_same_old_and_new_is_not_proof(self):
        r = analyze(fixture(old=0, loaded=0, taken=True))
        self.assertEqual(r['branches_comparing_pre_retirement_loaded_register'], 1)
        self.assertFalse(r['original_ps1_execution_authenticated'])

    def test_bne_immediate_and_after_gap_have_opposite_results(self):
        r0 = analyze(fixture(old=0, loaded=1, op=BNE_T0_ZERO, taken=False))
        r1 = analyze(fixture(old=0, loaded=1, gap=True,
                             op=BNE_T0_ZERO, taken=True))
        self.assertEqual(r0['branches_comparing_pre_retirement_loaded_register'], 1)
        self.assertEqual(r1['branches_comparing_pre_retirement_loaded_register'], 0)

    def test_unknown_initial_register_is_not_invented(self):
        data = fixture()
        del data['initial_gprs_u32']['8']
        with self.assertRaisesRegex(ValueError, 'missing GPR'):
            analyze(data)

    def test_missing_loaded_value_rejected(self):
        data = fixture()
        del data['steps'][0]['load_result_u32']
        with self.assertRaisesRegex(ValueError, 'load result'):
            analyze(data)

    def test_nop_branch_slot_required(self):
        data = fixture()
        data['steps'][2]['word_u32'] = f'0x{ADDU_T0_T0_ZERO:08x}'
        with self.assertRaisesRegex(ValueError, 'branch NOP slot'):
            analyze(data)

    def test_wrong_branch_target_and_skipped_delay_pc_rejected(self):
        for slot in (3, 5):
            with self.subTest(slot=slot):
                data = fixture()
                data['steps'][-1]['pc_u32'] = f'0x{BASE_PC + slot*4:08x}'
                if slot == 3:
                    data['steps'].pop(2)
                with self.assertRaises(ValueError):
                    analyze(data)

    def test_unsupported_branch_likely_and_jump_rejected(self):
        for op in (0x51000002, 0x08000000, 0x01000008):
            with self.subTest(word=op):
                data = fixture()
                data['steps'][1]['word_u32'] = f'0x{op:08x}'
                with self.assertRaisesRegex(ValueError, 'unsupported opcode'):
                    analyze(data)

    def test_simultaneous_delayed_write_and_direct_write_refused(self):
        data = fixture()
        data['steps'][1] = step(1, ADDU_T0_T0_ZERO)
        data['steps'][2] = step(2, BEQ_T0_ZERO_TAKEN, claimed_taken=False)
        data['steps'].append(step(3, 0))
        with self.assertRaisesRegex(ValueError, 'simultaneous'):
            analyze(data)

    def test_overlapping_loads_to_same_register_refused(self):
        data = fixture()
        data['steps'][1] = step(1, LW_T0_A0_NEXT,
                                load_result_u32='0x00000002')
        with self.assertRaisesRegex(ValueError, 'overlapping LW'):
            analyze(data)

    def test_invalid_lw_address_and_wrapping_rejected(self):
        data = fixture()
        data['initial_gprs_u32']['4'] = '0x80120002'
        with self.assertRaisesRegex(ValueError, 'unaligned LW'):
            analyze(data)
        data['initial_gprs_u32']['4'] = '0xfffffffc'
        data['steps'][0]['word_u32'] = '0x8c880004'
        with self.assertRaisesRegex(ValueError, 'wrapped'):
            analyze(data)

    def test_external_capture_label_does_not_authenticate_hardware(self):
        r = analyze(fixture(source='external_ps1_capture_claim'))
        self.assertTrue(r['claimed_external_capture'])
        self.assertFalse(r['original_ps1_execution_authenticated'])
        self.assertFalse(r['original_ps1_pipeline_cycle_accuracy_verified'])

    def test_repeated_or_unaligned_pc_rejected(self):
        for field in ('repeated', 'unaligned'):
            with self.subTest(field=field):
                data = fixture()
                if field == 'repeated':
                    data['steps'][-1]['pc_u32'] = data['steps'][2]['pc_u32']
                else:
                    data['steps'][0]['pc_u32'] = '0x80010001'
                with self.assertRaises(ValueError):
                    analyze(data)

    def test_no_branch_or_no_load_does_not_certify_pipeline(self):
        data = fixture()
        data['steps'][1] = step(1, 0)
        with self.assertRaises(ValueError):
            analyze(data)
        data = fixture()
        data['steps'][0] = step(0, 0)
        with self.assertRaises(ValueError):
            analyze(data)

    def test_boolean_initial_register_key_and_unknown_field_refused(self):
        for field in ('bad-key', 'unexpected', 'bool-word', 'wrong-source'):
            with self.subTest(field=field):
                data = fixture()
                if field == 'bad-key':
                    data['initial_gprs_u32']['32'] = '0x00000001'
                elif field == 'unexpected':
                    data['steps'][1]['PRIVATE_REGISTER_VALUE'] = 'secret'
                elif field == 'bool-word':
                    data['steps'][0]['load_result_u32'] = 1
                else:
                    data['source'] = 'confirmed_genuine_ps1'
                with self.assertRaises(ValueError):
                    analyze(data)

    def test_maximum_steps_enforced(self):
        data = fixture()
        data['steps'] = [step(i, 0) for i in range(33)]
        with self.assertRaisesRegex(ValueError, 'invalid claimed registers or steps'):
            analyze(data)

    def test_private_cli_success_and_sanitized_input_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'PRIVATE_REGISTER_0x80120000.json'
            path.write_text(json.dumps(fixture()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = main([str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(out.getvalue())['schema'], REPORT_SCHEMA)
            self.assertNotIn('0x8012', out.getvalue())
            self.assertNotIn('0x8001', out.getvalue())
            self.assertNotIn('PRIVATE_REGISTER', out.getvalue())

            path.write_text('{PRIVATE_RAW_RAM_0x80120000')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = main([str(path)])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(out.getvalue())['error_code'],
                             'invalid_private_input')
            self.assertNotIn('PRIVATE_', out.getvalue())
            self.assertNotIn('Traceback', out.getvalue())

    def test_missing_and_oversized_private_capture_are_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'PRIVATE_MISSING.json'
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(path)]), 2)
            self.assertNotIn('PRIVATE_MISSING', out.getvalue())
            path.write_bytes(b'{' + b'X' * MAX_FILE_BYTES)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(path)]), 2)
            self.assertEqual(json.loads(out.getvalue())['valid_input'], False)


if __name__ == '__main__':
    unittest.main()
