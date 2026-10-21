"""Synthetic-only cross-slot tests for candidate CDFLR shared regions."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdflr_region_families import audit_regions  # noqa: E402

STRIDE = 8192


def make_slot(variant=0, opaque=False, short_palettes=False, fault=None):
    offsets = []
    pos = 256
    for index in range(58):
        offsets.append(pos)
        if index < 42:
            pos += 4
        elif index % 2 == 0:
            pos += (224 if index == 42 else 64 if index == 44 else 512) if short_palettes else 512
        else:
            pos += 96
    payload = bytearray(STRIDE)
    for index, offset in enumerate(offsets):
        struct.pack_into("<I", payload, index * 4, 0x80183000 + offset)
    if opaque:
        payload[232:256] = bytes(range(1, 25))
    for index in range(42, 58):
        offset = offsets[index]
        if index % 2 == 0:
            length = offsets[index + 1] - offset
            for color in range(length // 2):
                value = color + (variant if index < 46 else index)
                struct.pack_into("<H", payload, offset + color * 2, value)
        else:
            struct.pack_into("<I", payload, offset, 0x8000)
            if index == 47:
                payload[offset + 8] = variant
    if fault == "ram_pointer":
        struct.pack_into("<I", payload, 57 * 4, 0xF1830000)
    elif fault == "unordered":
        struct.pack_into("<I", payload, 56 * 4, 0x80183000 + offsets[55])
    elif fault == "base":
        struct.pack_into("<I", payload, 0, 0x80000000)
    return bytes(payload)


def inspect(blob, stride=STRIDE):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.bin"
        path.write_bytes(blob)
        return audit_regions(path, stride)


def entry(report, index):
    return next(f for f in report["families"] if f["pointer_index"] == index)


class CDFLRRegionFamilyTests(unittest.TestCase):
    def test_shared_and_variable_segments(self):
        result = inspect(make_slot() + make_slot(variant=2, opaque=True))
        self.assertEqual(result["slot_count"], 2)
        self.assertEqual(result["zero_opaque_header_trailer_slots"], [0])
        self.assertEqual(result["invariant_candidate_palette_indices"], [46, 48, 50, 52, 54, 56])
        self.assertEqual(result["invariant_paired_data_indices"], [43, 45, 49, 51, 53, 55, 57])
        self.assertEqual(entry(result, 42)["unique_content_hash_count"], 2)
        self.assertEqual(entry(result, 46)["unique_content_hash_count"], 1)
        self.assertEqual(entry(result, 47)["unique_content_hash_count"], 2)
        self.assertEqual(entry(result, 46)["u16_count_range"], [256, 256])
        self.assertFalse(result["interpretation"]["original_payload_bytes_emitted"])

    def test_two_nonstandard_palette_lengths_are_preserved(self):
        result = inspect(make_slot() + make_slot(1, True, True))
        self.assertEqual(entry(result, 42)["non512_slot_indices"], [1])
        self.assertEqual(entry(result, 44)["non512_slot_indices"], [1])
        self.assertEqual(entry(result, 42)["u16_count_range"], [112, 256])
        self.assertEqual(entry(result, 44)["u16_count_range"], [32, 256])

    def test_last_region_extent_not_claimed_as_true_length(self):
        result = inspect(make_slot())
        self.assertTrue(entry(result, 57)["last_region_extent_is_upper_bound_only"])
        self.assertTrue(result["interpretation"]["last_region_size_is_upper_bound_only"])

    def test_unaligned_or_invalid_candidate_pointer_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid candidate pointer table"):
            inspect(make_slot(fault="ram_pointer"))

    def test_pointer_order_and_bad_base_rejected(self):
        with self.assertRaisesRegex(ValueError, "not increasing"):
            inspect(make_slot(fault="unordered"))
        with self.assertRaisesRegex(ValueError, "implausible RAM base"):
            inspect(make_slot(fault="base"))

    def test_invalid_slot_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            inspect(make_slot()[:-4])
        with self.assertRaisesRegex(ValueError, "invalid aligned"):
            inspect(make_slot(), 3)

    def test_all_identical_slots_are_reported_without_claiming_cluts(self):
        result = inspect(make_slot() * 3)
        for f in result["families"]:
            self.assertEqual(f["unique_content_hash_count"], 1)
            self.assertEqual(f["largest_identical_group_size"], 3)
        self.assertTrue(result["interpretation"]["u16_color_like_words_not_verified_ps1_clut"])


if __name__ == "__main__":
    unittest.main()
