"""Synthetic-only tests for the conservative post-index pointer-use audit."""
import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_verify_record_stride import three_signature_exe
from tools.verify_record_stride import TARGETS
from tools.audit_record_pointer_use import inspect, main

BASE = 0x80011420
ADDU_V1_V1_V0 = 0x00621821
ADDU_V1_V0_V1 = 0x00431821
LW_A0_V1 = 0x8c640000
SH_A0_V1 = 0xa4640002


def word_at(data, site, index, word):
    struct.pack_into('<I', data, 2048 + site - BASE + 4*index, word)


class RecordPointerUseTests(unittest.TestCase):
    def test_prefix_only_never_implies_pointer_access(self):
        result = inspect(three_signature_exe())
        self.assertEqual(result['matched_prefix_sites'], 3)
        self.assertEqual(result['static_index_coefficient'], 2708)
        self.assertEqual(result['direct_add_and_memory_access_patterns'], 0)
        self.assertEqual(result['unresolved_post_index_patterns'], 3)
        self.assertFalse(result['record_size_verified'])
        self.assertFalse(result['executed_pointer_use_verified'])

    def test_direct_add_and_load_pattern_at_three_sites(self):
        data = three_signature_exe()
        for site in TARGETS:
            word_at(data, site, 11, ADDU_V1_V1_V0)
            word_at(data, site, 12, LW_A0_V1)
        r = inspect(data)
        self.assertEqual(r['direct_add_and_memory_access_patterns'], 3)
        self.assertEqual(r['unresolved_post_index_patterns'], 0)
        self.assertFalse(r['record_size_verified'])
        self.assertTrue(r['syntactic_evidence_only'])
        self.assertNotIn('0x8006', str(r))
        self.assertNotIn('field_offset', str(r))

    def test_reverse_add_and_store_are_syntactic_only(self):
        data = three_signature_exe()
        word_at(data, TARGETS[0], 11, ADDU_V1_V0_V1)
        word_at(data, TARGETS[0], 12, 0)
        word_at(data, TARGETS[0], 13, SH_A0_V1)
        r = inspect(data)
        self.assertEqual(r['direct_add_and_memory_access_patterns'], 1)
        self.assertEqual(r['unresolved_post_index_patterns'], 2)
        self.assertFalse(r['playstation_hardware_equivalence_verified'])

    def test_one_site_add_without_access_is_counted_separately(self):
        data = three_signature_exe()
        # Use the first distant site: the other two windows overlap,
        # so their non-NOP signatures naturally terminate this scan.
        word_at(data, TARGETS[0], 11, ADDU_V1_V1_V0)
        r = inspect(data)
        self.assertEqual(r['add_without_memory_access_patterns'], 1)
        self.assertEqual(r['unresolved_post_index_patterns'], 2)

    def test_overlapping_next_signature_does_not_prove_missing_access(self):
        data = three_signature_exe()
        # The second target lies close to the third, so scanning ten
        # suffix words encounters the next prefix. Do not call that
        # a clean straight-line add with no memory access.
        word_at(data, TARGETS[1], 11, ADDU_V1_V1_V0)
        r = inspect(data)
        self.assertEqual(r['add_without_memory_access_patterns'], 0)
        self.assertEqual(r['unresolved_post_index_patterns'], 3)

    def test_control_flow_prevents_false_direct_path_claim(self):
        data = three_signature_exe()
        # An unconditional J before pointer addition terminates the
        # strictly linear syntactic scan, even if later bytes look valid.
        word_at(data, TARGETS[0], 11, 0x08000000)
        word_at(data, TARGETS[0], 12, ADDU_V1_V1_V0)
        word_at(data, TARGETS[0], 13, LW_A0_V1)
        r = inspect(data)
        self.assertEqual(r['direct_add_and_memory_access_patterns'], 0)
        self.assertEqual(r['unresolved_post_index_patterns'], 3)

    def test_memory_before_pointer_add_is_unresolved(self):
        data = three_signature_exe()
        word_at(data, TARGETS[2], 11, LW_A0_V1)
        word_at(data, TARGETS[2], 12, ADDU_V1_V1_V0)
        r = inspect(data)
        self.assertEqual(r['direct_add_and_memory_access_patterns'], 0)
        self.assertEqual(r['unresolved_post_index_patterns'], 3)

    def test_unrecognized_intermediate_instruction_fails_closed(self):
        data = three_signature_exe()
        word_at(data, TARGETS[1], 11, ADDU_V1_V1_V0)
        word_at(data, TARGETS[1], 12, 0x24420004)
        word_at(data, TARGETS[1], 13, LW_A0_V1)
        r = inspect(data)
        self.assertEqual(r['direct_add_and_memory_access_patterns'], 0)
        self.assertEqual(r['unresolved_post_index_patterns'], 3)

    def test_changed_second_signature_refuses_entire_report(self):
        data = three_signature_exe()
        off = 2048 + TARGETS[1] - BASE
        data[off] ^= 1
        with self.assertRaisesRegex(ValueError, 'record index signature'):
            inspect(data)

    def test_all_sites_need_complete_syntactic_window(self):
        data = three_signature_exe()
        data[0x1c:0x20] = (TARGETS[2] + 44 - BASE).to_bytes(4, 'little')
        with self.assertRaisesRegex(ValueError, 'window outside EXE'):
            inspect(data)

    def test_invalid_or_oversized_exe_rejected(self):
        for bad in (b'', b'PS-X EXE', b'not a game'):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                inspect(bad)
        data = three_signature_exe()
        data[0x1c:0x20] = (4 * 1024 * 1024 + 1).to_bytes(4, 'little')
        with self.assertRaisesRegex(ValueError, 'bounded EXE'):
            inspect(data)

    def test_private_disc_cli_reports_only_counts_and_flags(self):
        data = three_signature_exe()
        for site in TARGETS:
            word_at(data, site, 11, ADDU_V1_V1_V0)
            word_at(data, site, 12, LW_A0_V1)
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / 'inventory.json'
            inventory.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                 'size': len(data), 'directory': False}]}))
            output = io.StringIO()
            with patch('tools.audit_record_pointer_use.read_raw_iso_entry',
                       return_value=data):
                with contextlib.redirect_stdout(output):
                    result = main(['/private/game.bin', str(inventory)])
            self.assertEqual(result, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report['direct_add_and_memory_access_patterns'], 3)
            self.assertFalse(report['private_game_data_emitted'])
            self.assertNotIn('/private', output.getvalue())
            self.assertNotIn('0x8006', output.getvalue())


if __name__ == '__main__':
    unittest.main()
