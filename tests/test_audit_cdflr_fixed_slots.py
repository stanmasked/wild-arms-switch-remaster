"""Synthetic-only tests for a complete fixed-slot CDFLR catalog."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdflr_fixed_slots import audit_fixed_slots  # noqa: E402

SLOT_BYTES = 8192


def slot(*, variant=0, shorter_palette=False, invalid_pointer=False):
    offsets = []
    cursor = 256
    for i in range(58):
        offsets.append(cursor)
        if i >= 42 and i % 2 == 0:
            cursor += 512
        else:
            cursor += 32
    data = bytearray(SLOT_BYTES)
    if shorter_palette:
        offsets[43] -= 16
    if invalid_pointer:
        offsets[40] = offsets[39]
    for i, offset in enumerate(offsets):
        struct.pack_into("<I", data, 4 * i, 0x80183000 + offset)
    for i in range(2, 41):
        start = offsets[i]
        struct.pack_into("<5I", data, start, 0x41, 0, 1, 12, 1)
    for i in range(42, 58, 2):
        struct.pack_into("<I", data, offsets[i + 1], 0x8000)
    data[-1] = variant
    return bytes(data)


def scan(contents, slot_bytes=SLOT_BYTES):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic-cdflr.bin"
        path.write_bytes(contents)
        return audit_fixed_slots(path, slot_bytes)


class FixedSlotCatalogTests(unittest.TestCase):
    def test_equal_stride_and_duplicate_slots(self):
        a = slot()
        b = slot(variant=7)
        report = scan(a + b + a)
        self.assertEqual(report["slot_count"], 3)
        self.assertEqual(report["slot_bytes"], SLOT_BYTES)
        self.assertEqual(report["unique_sha256_count"], 2)
        self.assertEqual(report["duplicate_groups"], [[0, 2]])
        self.assertEqual(report["slots_with_58_pointers"], 3)
        self.assertEqual(report["slots_with_39_type_0x41_headers"], 3)
        self.assertEqual(report["slots_with_39_matching_span_rules"], 3)
        self.assertEqual(report["slots_with_all_8_palette_sized_spans"], 3)
        self.assertEqual(report["slots_with_all_8_data_markers"], 3)
        self.assertEqual(report["distinct_candidate_ram_bases"], ["0x80183000"])
        self.assertFalse(report["interpretation"]["original_payload_bytes_emitted"])

    def test_short_palette_is_reported_and_not_silently_dropped(self):
        report = scan(slot(shorter_palette=True))
        self.assertEqual(report["slots_with_all_8_palette_sized_spans"], 0)
        self.assertEqual(report["palette_size_exception_slot_indices"], [0])
        self.assertEqual(report["slots"][0]["palette_size_exception_indices"], [42])

    def test_incorrect_pointer_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "pointer order"):
            scan(slot(invalid_pointer=True))

    def test_bad_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            scan(slot()[:-1])
        with self.assertRaisesRegex(ValueError, "slot_bytes"):
            scan(slot(), slot_bytes=3)

    def test_missing_terminator_rejected(self):
        data = bytearray(slot())
        struct.pack_into("<I", data, 58 * 4, 0x1234)
        with self.assertRaisesRegex(ValueError, "terminator"):
            scan(bytes(data))

    def test_pointer_outside_record_rejected(self):
        data = bytearray(slot())
        struct.pack_into("<I", data, 57 * 4, 0x80183000 + SLOT_BYTES)
        with self.assertRaisesRegex(ValueError, "bounds"):
            scan(bytes(data))

    def test_variable_length_rule_corruption_is_detected(self):
        data = bytearray(slot())
        # Corrupt the length field without changing the pointer table.
        index_2_offset = 256 + 2 * 32
        struct.pack_into("<I", data, index_2_offset + 12, 16)
        report = scan(bytes(data))
        self.assertEqual(report["slots_with_39_type_0x41_headers"], 1)
        self.assertEqual(report["slots_with_39_matching_span_rules"], 0)
        self.assertEqual(report["slots"][0]["type_0x41_span_rule_matches"], 38)


if __name__ == "__main__":
    unittest.main()
