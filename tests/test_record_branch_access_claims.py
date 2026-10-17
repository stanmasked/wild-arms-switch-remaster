"""Synthetic regressions for PS1 branch-delay claimed traces; no game data."""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_executed_access_claims import claim, _hex, BASE, SCALE
from tests.test_record_pointer_use import ADDU_V1_V1_V0, LW_A0_V1, word_at
from tests.test_record_base_provenance import branch
from tools.verify_record_stride import TARGETS
from tools.mips_record_branch_trace import validate
from tools.audit_record_branch_access_claims import SCHEMA, analyze, main
from tools.audit_record_executed_access_claims import analyze as linear_analyze


def fixture(op=4, rs=8, rt=9, taken=True):
    exe, ref = claim()
    pc = TARGETS[0]
    word_at(exe, pc, 11, branch(op, rs, rt, 3))
    word_at(exe, pc, 12, 0)
    word_at(exe, pc, 13, ADDU_V1_V1_V0)
    word_at(exe, pc, 14, LW_A0_V1)
    word_at(exe, pc, 15, ADDU_V1_V1_V0)
    word_at(exe, pc, 16, LW_A0_V1)
    paths = (list(range(13)) + ([15, 16] if taken else [13, 14]))
    for row in ref['observations'][0]['samples']:
        row['executed_pcs'] = [_hex(pc + i * 4) for i in paths]
    ref['exe_sha256'] = hashlib.sha256(exe).hexdigest()
    return exe, ref


class BranchAccessClaimsTests(unittest.TestCase):
    def test_unknown_beq_taken_path_validates_delay_slot_and_numeric_evidence(self):
        exe, ref = fixture()
        report = analyze(exe, ref)
        self.assertTrue(report['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(report['claimed_nop_delay_slots_validated'], 3)
        self.assertEqual(report['claimed_unknown_branch_predicates'], 3)
        self.assertEqual(report['candidate_delay_aware_memory_access_sites'], 2)
        self.assertFalse(report['observed_branch_predicate_authenticated'])
        self.assertFalse(report['hardware_cycle_accurate_load_delay_verified'])
        self.assertFalse(report['original_ps1_hardware_execution_verified'])
        self.assertFalse(report['original_game_record_size_verified'])

    def test_unknown_beq_fallthrough_path_is_permitted_as_a_claim(self):
        exe, ref = fixture(taken=False)
        self.assertTrue(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_two_branch_outcomes_across_three_distinct_indices(self):
        exe, ref = fixture()
        pc = TARGETS[0]
        row = ref['observations'][0]['samples'][1]
        row['executed_pcs'] = [_hex(pc + i * 4)
                               for i in list(range(13)) + [13, 14]]
        r = analyze(exe, ref)
        self.assertTrue(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['claimed_unknown_branch_predicates'], 3)
        self.assertEqual(r['cross_site_address_comparisons_matching'], 3)

    def test_beq_same_register_must_take_branch(self):
        exe, ref = fixture(rs=8, rt=8)
        good = analyze(exe, ref)
        self.assertTrue(good['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(good['claimed_unknown_branch_predicates'], 0)
        pc = TARGETS[0]
        ref['observations'][0]['samples'][0]['executed_pcs'] = [
            _hex(pc + i * 4) for i in list(range(13)) + [13, 14]]
        bad = analyze(exe, ref)
        self.assertFalse(bad['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(bad['claimed_execution_sequences_matching_static_code'], 5)

    def test_bne_same_register_must_not_take_branch(self):
        exe, ref = fixture(op=5, rs=8, rt=8, taken=False)
        self.assertTrue(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])
        pc = TARGETS[0]
        ref['observations'][0]['samples'][2]['executed_pcs'] = [
            _hex(pc + i * 4) for i in list(range(13)) + [15, 16]]
        self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_bne_with_unknown_predicate_accepts_both_claimed_arms(self):
        for arm in (True, False):
            with self.subTest(taken=arm):
                exe, ref = fixture(op=5, taken=arm)
                result = analyze(exe, ref)
                self.assertTrue(result['claimed_data_consistent_with_checked_in_code'])
                self.assertEqual(result['claimed_unknown_branch_predicates'], 3)

    def test_missing_delay_slot_in_claim_is_rejected(self):
        exe, ref = fixture()
        ref['observations'][0]['samples'][1]['executed_pcs'].pop(12)
        result = analyze(exe, ref)
        self.assertFalse(result['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(result['claimed_execution_sequences_matching_static_code'], 5)

    def test_non_nop_delay_slot_rejected_even_if_pc_order_looks_plausible(self):
        exe, ref = fixture()
        word_at(exe, TARGETS[0], 12, ADDU_V1_V1_V0)
        ref['exe_sha256'] = hashlib.sha256(exe).hexdigest()
        self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_wrong_branch_destination_rejected(self):
        exe, ref = fixture()
        pc = TARGETS[0]
        ref['observations'][0]['samples'][0]['executed_pcs'] = [
            _hex(pc + i * 4) for i in list(range(13)) + [14, 16]]
        self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_wrong_encoded_immediate_rejects_old_pc_claim(self):
        exe, ref = fixture()
        word_at(exe, TARGETS[0], 11, branch(4, 8, 9, 4))
        ref['exe_sha256'] = hashlib.sha256(exe).hexdigest()
        self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_branch_likely_and_unconditional_jump_are_not_modeled(self):
        for word in (branch(20, 8, 9, 3), 0x08000000,
                     0x01000008, 0x0c000000):
            with self.subTest(word=word):
                exe, ref = fixture()
                word_at(exe, TARGETS[0], 11, word)
                ref['exe_sha256'] = hashlib.sha256(exe).hexdigest()
                self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_backwards_and_outside_window_branches_refused(self):
        for imm in (0, -3, 100):
            with self.subTest(imm=imm):
                exe, ref = fixture()
                word_at(exe, TARGETS[0], 11, branch(4, 8, 9, imm))
                ref['exe_sha256'] = hashlib.sha256(exe).hexdigest()
                self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_unrecognized_load_after_add_and_before_access_refused(self):
        exe, ref = fixture()
        word_at(exe, TARGETS[0], 15, LW_A0_V1)
        ref['exe_sha256'] = hashlib.sha256(exe).hexdigest()
        self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_alignment_and_field_displacement_still_enforced(self):
        exe, ref = fixture()
        for row in ref['observations'][0]['samples']:
            row['effective_address_u32'] = _hex(
                int(row['effective_address_u32'], 16) + 2)
        self.assertFalse(analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])

    def test_original_linear_mode_still_rejects_branch_trace(self):
        exe, ref = fixture()
        self.assertFalse(linear_analyze(exe, ref)['claimed_data_consistent_with_checked_in_code'])
        plain_exe, plain_ref = claim()
        self.assertTrue(linear_analyze(plain_exe, plain_ref)[
            'claimed_data_consistent_with_checked_in_code'])
        self.assertTrue(analyze(plain_exe, plain_ref)[
            'claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(analyze(plain_exe, plain_ref)[
            'claimed_nop_delay_slots_validated'], 0)

    def test_three_site_branchless_case_keeps_cross_site_relationships(self):
        exe, ref = claim(sites=(0, 1, 2), field_offsets=(0, 4, 8))
        r = analyze(exe, ref)
        self.assertTrue(r['claimed_data_consistent_with_checked_in_code'])
        self.assertEqual(r['signature_checked_sites'], 3)
        self.assertEqual(r['cross_site_address_comparisons_checked'], 9)

    def test_different_claimed_source_does_not_prove_hardware_origin(self):
        exe, ref = fixture()
        ref['source'] = 'external_ps1_capture_claim'
        r = analyze(exe, ref)
        self.assertTrue(r['claimed_external_capture'])
        self.assertFalse(r['runtime_instruction_provenance_verified'])
        self.assertFalse(r['actual_runtime_pc_provenance_authenticated'])

    def test_private_cli_has_success_mismatch_and_sanitized_failure(self):
        exe, ref = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            inv = Path(tmp) / 'inventory.json'
            inv.write_text(json.dumps({'entries': [{
                'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                'size': len(exe), 'directory': False}]}))
            private = Path(tmp) / 'PRIVATE_ADDRESS_0x80120000.json'
            private.write_text(json.dumps(ref))

            def call():
                output = io.StringIO()
                with patch('tools.audit_record_branch_access_claims.read_raw_iso_entry',
                           return_value=exe):
                    with contextlib.redirect_stdout(output):
                        status = main(['/private/game.bin', str(inv), str(private)])
                return status, output.getvalue()

            status, output = call()
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output)['schema'], SCHEMA)
            self.assertNotIn('PRIVATE_ADDRESS', output)
            self.assertNotIn('0x8012', output)
            self.assertNotIn('0x8006', output)

            ref['observations'][0]['samples'][1]['executed_pcs'].pop(12)
            private.write_text(json.dumps(ref))
            status, output = call()
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(output)['claimed_data_consistent_with_checked_in_code'])

            private.write_text('{PRIVATE_REGISTER_0x80010000')
            status, output = call()
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_REGISTER', output)
            self.assertNotIn('/private/', output)

    def test_validator_refuses_partial_prefix_and_non_word_addresses(self):
        exe, ref = fixture()
        pcs = tuple(int(p, 16) for p in
                    ref['observations'][0]['samples'][0]['executed_pcs'])
        # A prefix PC change, or an unaligned effective word address,
        # does not validate a claimed branch path.
        words = [int.from_bytes(exe[2048 + TARGETS[0] - 0x80011420 + 4*i:
                                  2048 + TARGETS[0] - 0x80011420 + 4*i + 4],
                                  'little') for i in range(21)]
        self.assertIsNone(validate(words, TARGETS[0],
                                   pcs[:4]+(pcs[4]+4,)+pcs[5:], 0, BASE))
        self.assertIsNone(validate(words, TARGETS[0], pcs, 0, BASE+2))


if __name__ == '__main__':
    unittest.main()
