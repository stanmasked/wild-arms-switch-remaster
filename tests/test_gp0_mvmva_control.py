import struct
import unittest
from tools.audit_gp0_mvmva_control import (
    EXPECTED_COMMAND_WORD, audit_executable, decode_mvmva)


class MvmvaControlTests(unittest.TestCase):
    def test_original_word(self):
        d = decode_mvmva(EXPECTED_COMMAND_WORD)
        self.assertEqual((d['matrix'], d['vector'], d['translation']),
                         ('rotation', 'V0', 'none'))
        self.assertEqual((d['sf'], d['shift_bits'], d['lm']), (1, 12, 0))
        self.assertTrue(d['known_original_word'])

    def test_all_matrix_selections(self):
        for index, name in enumerate(('rotation', 'light', 'color', 'reserved')):
            with self.subTest(index=index):
                word = (EXPECTED_COMMAND_WORD & ~(3 << 17)) | index << 17
                self.assertEqual(decode_mvmva(word)['matrix'], name)

    def test_all_vector_selections(self):
        for index, name in enumerate(('V0', 'V1', 'V2', 'IR')):
            word = (EXPECTED_COMMAND_WORD & ~(3 << 15)) | index << 15
            self.assertEqual(decode_mvmva(word)['vector'], name)

    def test_all_translation_selections(self):
        for index, name in enumerate(('TR', 'BK', 'FC', 'none')):
            word = (EXPECTED_COMMAND_WORD & ~(3 << 13)) | index << 13
            self.assertEqual(decode_mvmva(word)['translation'], name)

    def test_sf_zero_no_shift(self):
        self.assertEqual(decode_mvmva(EXPECTED_COMMAND_WORD & ~(1 << 19))['shift_bits'], 0)

    def test_lm_one(self):
        self.assertEqual(decode_mvmva(EXPECTED_COMMAND_WORD | (1 << 10))['lm'], 1)

    def test_reject_wrong_cop2_opcode(self):
        self.assertIsNone(decode_mvmva(EXPECTED_COMMAND_WORD ^ (1 << 26)))

    def test_reject_non_command_cop2(self):
        self.assertIsNone(decode_mvmva(EXPECTED_COMMAND_WORD & ~(1 << 25)))

    def test_reject_wrong_function(self):
        self.assertIsNone(decode_mvmva(EXPECTED_COMMAND_WORD ^ 1))

    def test_executable_location_and_exact_word(self):
        base = 0x800B68F8
        b = struct.pack('<II', 0, EXPECTED_COMMAND_WORD)
        report = audit_executable(b, base)
        self.assertTrue(report['matched_original_command'])
        self.assertEqual(report['command']['mx'], 0)

    def test_altered_executable_word_does_not_verify_original(self):
        report = audit_executable(struct.pack('<I', EXPECTED_COMMAND_WORD ^ (1 << 10)),
                                  0x800B68FC)
        self.assertFalse(report['matched_original_command'])
        self.assertIsNotNone(report['command'])

    def test_missing_or_misaligned_location(self):
        self.assertFalse(audit_executable(b'', 0)['matched_original_command'])
        self.assertFalse(audit_executable(b'\0' * 8, 0x800B68FD)['matched_original_command'])


if __name__ == '__main__':
    unittest.main()
