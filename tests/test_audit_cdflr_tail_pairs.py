"""Synthetic-only checks of alternating CDFLR tail signatures."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdflr_tail_pairs import audit_tail  # noqa: E402


def synthetic():
    offsets = []
    cursor = 256
    for index in range(58):
        offsets.append(cursor)
        if index >= 42:
            cursor += 512 if index % 2 == 0 else 1024
        else:
            cursor += 4
    data = bytearray(cursor)
    for index, offset in enumerate(offsets):
        struct.pack_into("<I", data, index * 4, 0x80183000 + offset)
        if index >= 42 and index % 2 == 0:
            for color_index in range(256):
                struct.pack_into("<H", data, offset + color_index * 2,
                                 color_index + index)
        elif index >= 43:
            struct.pack_into("<I", data, offset, 0x8000)
    return data, offsets


def inspect(data):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.bin"
        path.write_bytes(data)
        return audit_tail(path)


class TailPairAuditTests(unittest.TestCase):
    def test_eight_complete_candidate_pairs_and_unknown_last_end(self):
        data, _ = synthetic()
        report = inspect(data)
        self.assertEqual(report["pointer_table_entries"], 58)
        self.assertEqual(report["candidate_palette_indices"], list(range(42, 57, 2)))
        self.assertEqual(report["candidate_data_indices"], list(range(43, 58, 2)))
        self.assertEqual(report["palette_exact_512_count"], 8)
        self.assertEqual(report["palette_distinct_u16_min"], 256)
        self.assertEqual(report["data_first_word_0x8000_count"], 8)
        self.assertEqual(report["bounded_next_pointer_data_span_count"], 7)
        self.assertEqual(report["bounded_next_pointer_data_span_min"], 1024)
        self.assertTrue(report["last_data_span_length_unknown"])
        self.assertFalse(report["interpretation"]["original_payload_emitted"])

    def test_misaligned_candidate_palette_span_is_reported_not_decoded(self):
        data, offsets = synthetic()
        struct.pack_into("<I", data, 43 * 4, 0x80183000 + offsets[43] + 4)
        report = inspect(data)
        self.assertEqual(report["palette_exact_512_count"], 7)
        self.assertIsNone(report["palette_candidates"][0]["distinct_u16_values_if_512"])

    def test_mismatched_candidate_data_prefix_is_counted(self):
        data, offsets = synthetic()
        struct.pack_into("<I", data, offsets[57], 0)
        report = inspect(data)
        self.assertEqual(report["data_first_word_0x8000_count"], 7)
        self.assertTrue(report["last_data_span_length_unknown"])

    def test_malformed_pointer_order_is_rejected(self):
        data, offsets = synthetic()
        struct.pack_into("<I", data, 47 * 4, 0x80183000 + offsets[46])
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            inspect(data)

    def test_bad_table_terminator_is_rejected(self):
        data, _ = synthetic()
        struct.pack_into("<I", data, 58 * 4, 1)
        with self.assertRaisesRegex(ValueError, "terminator"):
            inspect(data)

    def test_target_out_of_bounds_is_rejected(self):
        data, _ = synthetic()
        struct.pack_into("<I", data, 57 * 4, 0x801FFFFC)
        with self.assertRaisesRegex(ValueError, "bounds"):
            inspect(data)


if __name__ == "__main__":
    unittest.main()
