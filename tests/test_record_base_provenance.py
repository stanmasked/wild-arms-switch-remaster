"""Synthetic-only guarded tests for base-pointer and branch provenance."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_verify_record_stride import three_signature_exe
from tests.test_record_pointer_use import (
    ADDU_V1_V1_V0, LW_A0_V1, word_at,
)
from tools.verify_record_stride import INDEX_WORDS, GLOBAL_WORDS, TARGETS
from tools.audit_record_base_provenance import (
    SCHEMA, _prefix_has_one_instruction_load_gap, _trace_tail, inspect, main,
)


def branch(op, rs, rt, offset):
    return (op << 26) | (rs << 21) | (rt << 16) | (offset & 0xffff)


class RecordBaseProvenanceTests(unittest.TestCase):
    def test_exact_lui_load_gap_is_syntactic_not_memory_capture(self):
        self.assertTrue(_prefix_has_one_instruction_load_gap(
            INDEX_WORDS + GLOBAL_WORDS))
        changed = list(INDEX_WORDS + GLOBAL_WORDS)
        changed[10] = 0
        with self.assertRaises(ValueError):
            _prefix_has_one_instruction_load_gap(changed)

    def test_three_matching_prefixes_without_tail_remain_unresolved(self):
        r = inspect(three_signature_exe())
        self.assertEqual(r['schema'], SCHEMA)
        self.assertEqual(r['matching_global_load_chain_sites'], 3)
        self.assertEqual(r['load_delay_gap_syntactically_present_sites'], 3)
        self.assertEqual(r['index_coefficient_from_checked_in_opcodes'], 2708)
        self.assertEqual(r['unresolved_sites'], 3)
        self.assertEqual(r['all_enumerated_paths_reach_candidate_access_sites'], 0)
        self.assertFalse(r['global_pointer_contents_known'])
        self.assertFalse(r['original_ps1_execution_verified'])
        self.assertFalse(r['record_size_verified'])
        self.assertFalse(r['native_switch_build_verified'])

    def test_straight_line_add_and_memory_at_all_three_sites(self):
        data = three_signature_exe()
        for target in TARGETS:
            word_at(data, target, 11, ADDU_V1_V1_V0)
            word_at(data, target, 12, LW_A0_V1)
        result = inspect(data)
        self.assertEqual(result['all_enumerated_paths_reach_candidate_access_sites'], 3)
        self.assertEqual(result['some_paths_reach_candidate_access_sites'], 0)
        self.assertEqual(result['unresolved_sites'], 0)
        self.assertFalse(result['private_game_data_emitted'])
        self.assertNotIn('0x8006', str(result))
        self.assertNotIn('0x800d', str(result))

    def test_known_beq_same_register_takes_branch_after_nop_slot(self):
        data = three_signature_exe()
        word_at(data, TARGETS[0], 11, branch(4, 8, 8, 3))
        word_at(data, TARGETS[0], 15, ADDU_V1_V1_V0)
        word_at(data, TARGETS[0], 16, LW_A0_V1)
        result = inspect(data)
        self.assertEqual(result['known_predicate_branches_examined'], 1)
        self.assertEqual(result['all_enumerated_paths_reach_candidate_access_sites'], 1)
        self.assertEqual(result['unresolved_sites'], 2)

    def test_known_bne_same_register_never_takes_branch(self):
        data = three_signature_exe()
        word_at(data, TARGETS[0], 11, branch(5, 8, 8, 3))
        word_at(data, TARGETS[0], 13, ADDU_V1_V1_V0)
        word_at(data, TARGETS[0], 14, LW_A0_V1)
        result = inspect(data)
        self.assertEqual(result['known_predicate_branches_examined'], 1)
        self.assertEqual(result['all_enumerated_paths_reach_candidate_access_sites'], 1)

    def test_unknown_beq_explores_two_paths_both_succeed(self):
        data = three_signature_exe()
        word_at(data, TARGETS[0], 11, branch(4, 8, 9, 3))
        for index in (13, 15):
            word_at(data, TARGETS[0], index, ADDU_V1_V1_V0)
            word_at(data, TARGETS[0], index + 1, LW_A0_V1)
        result = inspect(data)
        self.assertEqual(result['unknown_predicate_branches_examined'], 1)
        self.assertEqual(result['all_enumerated_paths_reach_candidate_access_sites'], 1)
        self.assertEqual(result['some_paths_reach_candidate_access_sites'], 0)

    def test_unknown_branch_one_path_unresolved_never_proves_all(self):
        data = three_signature_exe()
        word_at(data, TARGETS[0], 11, branch(4, 8, 9, 3))
        word_at(data, TARGETS[0], 13, ADDU_V1_V1_V0)
        word_at(data, TARGETS[0], 14, LW_A0_V1)
        result = inspect(data)
        self.assertEqual(result['some_paths_reach_candidate_access_sites'], 1)
        self.assertEqual(result['all_enumerated_paths_reach_candidate_access_sites'], 0)
        self.assertFalse(result['original_ps1_execution_verified'])

    def test_control_instruction_in_delay_slot_is_unresolved(self):
        data = three_signature_exe()
        word_at(data, TARGETS[0], 11, branch(4, 8, 8, 3))
        word_at(data, TARGETS[0], 12, ADDU_V1_V1_V0)
        word_at(data, TARGETS[0], 15, LW_A0_V1)
        result = inspect(data)
        self.assertEqual(result['unresolved_sites'], 3)

    def test_branch_likely_and_indirect_jump_remain_unresolved(self):
        for word in (branch(20, 8, 8, 3), 0x01000008, 0x08000000):
            with self.subTest(word=word):
                data = three_signature_exe()
                word_at(data, TARGETS[0], 11, word)
                word_at(data, TARGETS[0], 13, ADDU_V1_V1_V0)
                word_at(data, TARGETS[0], 14, LW_A0_V1)
                self.assertEqual(inspect(data)['unresolved_sites'], 3)

    def test_bad_branch_destination_into_slot_or_out_of_window(self):
        for offset in (0, -2, 200):
            with self.subTest(offset=offset):
                data = three_signature_exe()
                word_at(data, TARGETS[0], 11, branch(4, 8, 8, offset))
                self.assertEqual(inspect(data)['unresolved_sites'], 3)

    def test_convergent_branch_paths_do_not_become_false_unknown(self):
        # Unknown branch: one route skips two NOPs, the other passes
        # through them. Both then enter the SAME (pc, added) state.
        # A duplicate BFS state must not produce a false unknown terminal.
        r = _trace_tail([
            branch(4, 8, 9, 3), 0, 0, 0, ADDU_V1_V1_V0, LW_A0_V1,
        ])
        self.assertEqual(r['success'], 1)
        self.assertEqual(r['unknown'], 0)
        self.assertEqual(r['unknown_branches'], 1)

    def test_signature_mutation_refuses_aggregate_output(self):
        data = three_signature_exe()
        off = 2048 + TARGETS[1] - 0x80011420
        data[off + 8 * 4] ^= 1
        with self.assertRaisesRegex(ValueError, 'signature'):
            inspect(data)

    def test_missing_window_and_invalid_image_fail_closed(self):
        data = three_signature_exe()
        data[0x1c:0x20] = (TARGETS[-1] + 44 - 0x80011420).to_bytes(4, 'little')
        with self.assertRaisesRegex(ValueError, 'window'):
            inspect(data)
        for bad in (b'', b'PS-X EXE', b'not an EXE'):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                inspect(bad)

    def test_private_cli_reports_only_safe_aggregate_fields(self):
        data = three_signature_exe()
        for target in TARGETS:
            word_at(data, target, 11, ADDU_V1_V1_V0)
            word_at(data, target, 12, LW_A0_V1)
        with tempfile.TemporaryDirectory() as temp:
            inv = Path(temp) / 'inventory.json'
            inv.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                 'size': len(data), 'directory': False}]}), encoding='utf-8')
            output = io.StringIO()
            with patch('tools.audit_record_base_provenance.read_raw_iso_entry',
                       return_value=data):
                with contextlib.redirect_stdout(output):
                    status = main(['/private/secret.bin', str(inv)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())[
                'all_enumerated_paths_reach_candidate_access_sites'], 3)
            self.assertNotIn('/private/', output.getvalue())
            self.assertNotIn('0x800', output.getvalue())

    def test_private_cli_sanitizes_missing_image_and_bad_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            inv = Path(temp) / 'inventory.json'
            inv.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                 'size': 2048, 'directory': False}]}), encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(['/private/SECRET-PATH.bin', str(inv)])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output.getvalue())['error_code'],
                             'invalid_private_input')
            self.assertNotIn('SECRET-PATH', output.getvalue())
            self.assertNotIn('Traceback', output.getvalue())
            inv.write_text('{PRIVATE_CORRUPTION', encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(['/private/secret.bin', str(inv)])
            self.assertEqual(status, 2)
            self.assertNotIn('PRIVATE_CORRUPTION', output.getvalue())


if __name__ == '__main__':
    unittest.main()
