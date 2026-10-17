import unittest
import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from tools.verify_record_stride import (
    INDEX_WORDS, GLOBAL_WORDS, TARGETS, stride_from_index_words, inspect_exe,
    inspect_index_scale_evidence, _static_index_scale, main,
)

def three_signature_exe():
    """Synthetic, zero-filled PS-X EXE with exactly three public opcode signatures."""
    base = 0x80011420
    data = bytearray(2048 + 0xc1800)
    data[:8] = b'PS-X EXE'
    data[0x18:0x1c] = base.to_bytes(4, 'little')
    data[0x1c:0x20] = (0xc1800).to_bytes(4, 'little')
    for target in TARGETS:
        offset = 2048 + target - base
        for i, word in enumerate(INDEX_WORDS + GLOBAL_WORDS):
            data[offset + 4*i:offset + 4*i+4] = word.to_bytes(4, 'little')
    return data


class RecordStrideTests(unittest.TestCase):
    def test_mips_arithmetic_exposes_unresolved_stride_discrepancy(self):
        # The checked-in eight instruction words evaluate to 677 index
        # units, and the subsequent SLL by 2 makes 2708, *not* 364.
        self.assertEqual(stride_from_index_words(INDEX_WORDS), 2708)
        self.assertNotEqual(stride_from_index_words(INDEX_WORDS), 364)
        self.assertEqual((INDEX_WORDS[4] >> 6) & 31, 3)

    def test_changed_opcode_rejected(self):
        x = list(INDEX_WORDS)
        x[0] = 0
        with self.assertRaises(ValueError):
            stride_from_index_words(x)

    def test_three_function_prefixes_do_not_certify_false_stride(self):
        data = three_signature_exe()
        # Matching opcodes alone cannot prove the legacy constant.
        with self.assertRaisesRegex(ValueError, 'unverified record stride'):
            inspect_exe(data)

    def test_independent_opcode_interpretation_confirms_index_coefficient(self):
        self.assertEqual(_static_index_scale(INDEX_WORDS, GLOBAL_WORDS), 2708)
        self.assertEqual(_static_index_scale(INDEX_WORDS, GLOBAL_WORDS),
                         stride_from_index_words(INDEX_WORDS))
        self.assertNotEqual(_static_index_scale(INDEX_WORDS, GLOBAL_WORDS), 364)

    def test_modified_opcode_or_final_shift_is_rejected(self):
        index = list(INDEX_WORDS)
        index[4] ^= 1 << 6  # Alter SLL shift amount.
        with self.assertRaises(ValueError):
            _static_index_scale(index, GLOBAL_WORDS)
        global_words = list(GLOBAL_WORDS)
        global_words[-1] ^= 1 << 6
        with self.assertRaises(ValueError):
            _static_index_scale(INDEX_WORDS, global_words)

    def test_three_signature_sites_expose_only_static_scale(self):
        report = inspect_index_scale_evidence(three_signature_exe())
        self.assertEqual(report['schema'],
                         'wild-arms-ps1-static-index-scale-evidence-v1')
        self.assertEqual(report['matched_index_sites'], 3)
        self.assertEqual(report['opcode_derived_index_scale_bytes'], 2708)
        self.assertFalse(report['legacy_364_byte_stride_consistent'])
        self.assertFalse(report['record_layout_verified'])
        self.assertFalse(report['original_hardware_execution_verified'])
        self.assertFalse(report['private_game_bytes_emitted'])
        self.assertNotIn('0x8006', str(report))
        self.assertNotIn('data_hex', str(report))

    def test_modified_second_site_is_fail_closed_without_partial_report(self):
        data = three_signature_exe()
        target = TARGETS[1]
        off = 2048 + target - 0x80011420
        data[off] ^= 1
        with self.assertRaisesRegex(ValueError, 'unexpected record index signature'):
            inspect_index_scale_evidence(data)

    def test_record_evidence_refuses_truncated_and_invalid_executables(self):
        for data in (b'', b'PS-X EXE', bytearray(b'not a PS-X EXE'),
                     three_signature_exe()[:2048]):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                inspect_index_scale_evidence(data)
        data = three_signature_exe()
        data[0x1c:0x20] = (4*1024*1024+1).to_bytes(4, 'little')
        with self.assertRaisesRegex(ValueError, 'invalid bounded EXE'):
            inspect_index_scale_evidence(data)

    def test_true_stride_never_inferred_from_synthetic_scale(self):
        data = three_signature_exe()
        self.assertEqual(inspect_index_scale_evidence(data)
                         ['opcode_derived_index_scale_bytes'], 2708)
        with self.assertRaisesRegex(ValueError, 'unverified record stride'):
            inspect_exe(data)

    def test_private_disc_cli_evidence_mode_emits_only_safe_fields(self):
        private = three_signature_exe()
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / 'inventory.json'
            inventory.write_text(json.dumps({'entries': [
                {'path': '/EXE/WILDARMS.EXE;1', 'lba': 0,
                 'size': len(private)}]}), encoding='utf-8')
            output = StringIO()
            with patch('sys.argv', ['record-stride', '/private/game.bin',
                                    str(inventory), '--index-evidence-only']):
                with patch('tools.verify_record_stride.read_raw_iso_entry',
                           return_value=private):
                    with contextlib.redirect_stdout(output):
                        main()
            report = json.loads(output.getvalue())
            self.assertEqual(report['matched_index_sites'], 3)
            self.assertEqual(report['opcode_derived_index_scale_bytes'], 2708)
            self.assertFalse(report['record_layout_verified'])
            self.assertNotIn('/private/game.bin', output.getvalue())
            self.assertNotIn('0x8006', output.getvalue())

    def test_invalid_executable(self):
        with self.assertRaises(ValueError):
            inspect_exe(b'invalid')

if __name__ == '__main__':
    unittest.main()
