"""Synthetic regressions for claimed PS1 global-slot capture chronology."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_record_global_slot_witness import fixture
from tests.test_record_pipeline_coupling import _hex
from tools.verify_record_stride import TARGETS
from tools.audit_record_global_slot_witness import analyze as previous_audit
from tools.audit_record_temporal_slot_snapshots import (
    SCHEMA, REPORT_SCHEMA, _read_snapshot, analyze, main,
)

SLOT = '0x800d2c3c'
VALUE = '0x80120000'


def temporal_fixture(*, sites=(0, 1)):
    exe, slot_claim = fixture(sites=sites)
    windows = []
    for i, witness in enumerate(slot_claim['slot_witnesses']):
        pc = TARGETS[int(witness['site'][-1])-1] + 36
        start = 10 + i * 3
        windows.append({
            'site': witness['site'],
            'record_index': witness['record_index'],
            'execution_tag': f'private-event-{i}',
            'lw_event_sequence': start + 1,
            'before': {
                'at_pc_u32': _hex(pc),
                'slot_address_u32': SLOT,
                'slot_word_u32': VALUE,
                'event_sequence': start,
                'collector_tag': 'memory_watch',
            },
            'after': {
                'at_pc_u32': _hex(pc + 8),
                'slot_address_u32': SLOT,
                'slot_word_u32': VALUE,
                'event_sequence': start + 2,
                'collector_tag': 'memory_snapshot',
            },
        })
    return exe, {
        'schema': SCHEMA,
        'slot_claim': slot_claim,
        'read_windows': windows,
    }


class TemporalSlotSnapshotsTests(unittest.TestCase):
    def test_six_windows_match_exe_slot_and_bounded_order(self):
        exe, record = temporal_fixture()
        result = analyze(exe, record)
        self.assertEqual(result['schema'], REPORT_SCHEMA)
        self.assertEqual(result['code_sites_with_exe_derived_slots'], 2)
        self.assertEqual(result['claimed_snapshot_windows_checked'], 6)
        self.assertEqual(result['temporal_slot_snapshot_pairs_matching'], 6)
        self.assertEqual(result['claimed_distinct_collector_pairs'], 6)
        self.assertTrue(result['claimed_event_sequences_nonoverlapping'])
        self.assertTrue(result['prior_global_slot_claims_consistent'])
        self.assertTrue(result['all_claimed_temporal_snapshots_consistent'])
        for field in ('independent_collection_provenance_authenticated',
                      'memory_contents_independently_observed',
                      'original_ps1_execution_verified',
                      'original_game_record_size_verified',
                      'native_nintendo_switch_build_verified',
                      'private_addresses_or_values_emitted'):
            self.assertFalse(result[field], field)
        self.assertNotIn('0x800d', str(result))
        self.assertNotIn('0x8012', str(result))

    def test_three_code_sites_and_nine_private_windows(self):
        exe, record = temporal_fixture(sites=(0, 1, 2))
        result = analyze(exe, record)
        self.assertTrue(result['all_claimed_temporal_snapshots_consistent'])
        self.assertEqual(result['claimed_snapshot_windows_checked'], 9)
        self.assertEqual(result['code_sites_with_exe_derived_slots'], 3)

    def test_window_input_order_is_not_treated_as_event_order(self):
        exe, record = temporal_fixture()
        record['read_windows'].reverse()
        self.assertTrue(analyze(exe, record)['all_claimed_temporal_snapshots_consistent'])

    def test_previous_stage240_remains_compatible(self):
        exe, record = temporal_fixture()
        old = previous_audit(exe, record['slot_claim'])
        self.assertTrue(old['all_private_global_slot_claims_consistent'])

    def test_wrong_memory_word_after_load_is_detected_without_value_output(self):
        exe, record = temporal_fixture()
        record['read_windows'][0]['after']['slot_word_u32'] = '0x80120010'
        result = analyze(exe, record)
        self.assertEqual(result['temporal_slot_snapshot_pairs_matching'], 5)
        self.assertFalse(result['all_claimed_temporal_snapshots_consistent'])
        self.assertTrue(result['prior_global_slot_claims_consistent'])
        self.assertNotIn('0x80120010', str(result))

    def test_wrong_word_before_load_is_detected(self):
        exe, record = temporal_fixture()
        record['read_windows'][0]['before']['slot_word_u32'] = '0x00000000'
        self.assertFalse(analyze(exe, record)['all_claimed_temporal_snapshots_consistent'])

    def test_wrong_snapshot_pc_before_or_after_lw_is_detected(self):
        for phase, value in [('before', _hex(TARGETS[0] + 40)),
                             ('after', _hex(TARGETS[0] + 40))]:
            with self.subTest(phase=phase):
                exe, record = temporal_fixture()
                record['read_windows'][0][phase]['at_pc_u32'] = value
                result = analyze(exe, record)
                self.assertEqual(result['temporal_slot_snapshot_pairs_matching'], 5)

    def test_kseg_physical_alias_is_not_implicitly_substituted(self):
        exe, record = temporal_fixture()
        record['read_windows'][0]['before']['slot_address_u32'] = '0xa00d2c3c'
        result = analyze(exe, record)
        self.assertFalse(result['all_claimed_temporal_snapshots_consistent'])
        self.assertEqual(result['temporal_slot_snapshot_pairs_matching'], 5)

    def test_wrong_slot_address_in_after_probe_is_detected(self):
        exe, record = temporal_fixture()
        record['read_windows'][0]['after']['slot_address_u32'] = '0x800d2c40'
        self.assertFalse(analyze(exe, record)['all_claimed_temporal_snapshots_consistent'])

    def test_same_collector_identifier_is_not_a_distinct_pair(self):
        exe, record = temporal_fixture()
        record['read_windows'][0]['after']['collector_tag'] = 'memory_watch'
        result = analyze(exe, record)
        self.assertEqual(result['claimed_distinct_collector_pairs'], 5)
        self.assertEqual(result['temporal_slot_snapshot_pairs_matching'], 5)
        self.assertFalse(result['independent_collection_provenance_authenticated'])

    def test_forged_distinct_labels_never_authenticate_provenance(self):
        exe, record = temporal_fixture()
        record['slot_claim']['joined_claim']['access_claim']['source'] = (
            'external_ps1_capture_claim')
        result = analyze(exe, record)
        self.assertTrue(result['all_claimed_temporal_snapshots_consistent'])
        self.assertFalse(result['independent_collection_provenance_authenticated'])

    def test_equal_reversed_and_noninteger_event_sequence_refused(self):
        for modification in ('equal', 'reversed', 'boolean', 'negative'):
            with self.subTest(modification=modification):
                exe, record = temporal_fixture()
                win = record['read_windows'][0]
                if modification == 'equal':
                    win['lw_event_sequence'] = win['before']['event_sequence']
                elif modification == 'reversed':
                    win['after']['event_sequence'] = win['before']['event_sequence']
                elif modification == 'boolean':
                    win['lw_event_sequence'] = True
                else:
                    win['before']['event_sequence'] = -1
                with self.assertRaises(ValueError):
                    analyze(exe, record)

    def test_interleaved_windows_and_reused_event_sequence_refused(self):
        exe, record = temporal_fixture()
        record['read_windows'][1]['before']['event_sequence'] = 11
        with self.assertRaisesRegex(ValueError, 'interleaved|reused'):
            analyze(exe, record)

    def test_missing_duplicate_foreign_windows_refused(self):
        for situation in ('missing', 'duplicate', 'foreign'):
            with self.subTest(situation=situation):
                exe, record = temporal_fixture()
                if situation == 'missing':
                    record['read_windows'].pop()
                elif situation == 'duplicate':
                    record['read_windows'][-1]['site'] = record['read_windows'][0]['site']
                    record['read_windows'][-1]['record_index'] = (
                        record['read_windows'][0]['record_index'])
                else:
                    record['read_windows'][-1]['site'] = 'site_4'
                with self.assertRaises(ValueError):
                    analyze(exe, record)

    def test_repeated_execution_tag_and_private_field_injection_refused(self):
        for bad in ('duplicate-tag', 'injected-private-field'):
            with self.subTest(bad=bad):
                exe, record = temporal_fixture()
                if bad == 'duplicate-tag':
                    record['read_windows'][1]['execution_tag'] = (
                        record['read_windows'][0]['execution_tag'])
                else:
                    record['read_windows'][0]['before']['PRIVATE_RAM_DUMP'] = (
                        'SECRET_MEMORY')
                with self.assertRaises(ValueError):
                    analyze(exe, record)

    def test_snapshot_rejects_unbounded_tags_and_invalid_address_types(self):
        for mutation in ('invalid-collector', 'oversized-execution',
                         'numeric-address', 'invalid-word'):
            with self.subTest(mutation=mutation):
                exe, record = temporal_fixture()
                if mutation == 'invalid-collector':
                    record['read_windows'][0]['before']['collector_tag'] = '../secret'
                elif mutation == 'oversized-execution':
                    record['read_windows'][0]['execution_tag'] = 'a' * 33
                elif mutation == 'numeric-address':
                    record['read_windows'][0]['before']['slot_address_u32'] = 0x800d2c3c
                else:
                    record['read_windows'][0]['after']['slot_word_u32'] = 'private'
                with self.assertRaises(ValueError):
                    analyze(exe, record)

    def test_captured_source_word_must_match_prior_slot_claim(self):
        exe, record = temporal_fixture()
        record['slot_claim']['slot_witnesses'][0]['slot_memory_word_u32'] = (
            '0x80120010')
        result = analyze(exe, record)
        self.assertFalse(result['prior_global_slot_claims_consistent'])
        self.assertFalse(result['all_claimed_temporal_snapshots_consistent'])

    def test_private_cli_coherent_contradictory_and_corrupt_are_sanitized(self):
        exe, record = temporal_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            inv = Path(tmp) / 'inventory.json'
            inv.write_text(json.dumps({'entries': [{
                'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                'size': len(exe), 'directory': False}]}))
            private = Path(tmp) / 'PRIVATE_MEMORY_0x800d2c3c.json'
            private.write_text(json.dumps(record))

            def command():
                output = io.StringIO()
                with patch('tools.audit_record_temporal_slot_snapshots.read_raw_iso_entry',
                           return_value=exe):
                    with contextlib.redirect_stdout(output):
                        status = main(['/private/WildArms.bin', str(inv),
                                       str(private)])
                return status, output.getvalue()

            code, output = command()
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)['all_claimed_temporal_snapshots_consistent'])
            for secret in ('PRIVATE_MEMORY', '/private/', '0x800d', '0x8012'):
                self.assertNotIn(secret, output)

            record['read_windows'][0]['after']['slot_word_u32'] = '0x80120010'
            private.write_text(json.dumps(record))
            code, output = command()
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)['all_claimed_temporal_snapshots_consistent'])
            self.assertNotIn('0x80120010', output)

            private.write_text('{PRIVATE_LW_REGISTER_VALUES')
            code, output = command()
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)['error_code'], 'invalid_private_input')
            self.assertNotIn('PRIVATE_LW_REGISTER_VALUES', output)
            self.assertNotIn('Traceback', output)

    def test_missing_private_file_path_and_original_data_do_not_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp)/'PRIVATE_SECRET_0x800d2c3c.json'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['/private/game.bin', '/private/inventory.json',
                             str(missing)])
            self.assertEqual(code, 2)
            self.assertFalse(json.loads(output.getvalue())[
                'private_addresses_or_values_emitted'])
            self.assertNotIn('PRIVATE_SECRET', output.getvalue())


if __name__ == '__main__':
    unittest.main()
