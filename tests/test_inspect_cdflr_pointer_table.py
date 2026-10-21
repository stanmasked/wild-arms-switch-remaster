"""Synthetic-only contract checks for CDFLR candidate pointer-table probing."""
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from inspect_cdflr_pointer_table import inspect_pointer_table  # noqa: E402


def image(addresses=(0x80183100, 0x80183140, 0x80183180), size=2048):
    data = bytearray(size)
    for i, address in enumerate(addresses):
        struct.pack_into("<I", data, i * 4, address)
    struct.pack_into("<5I", data, 256, 0x41, 0, 1, 20, 4)
    struct.pack_into("<5I", data, 320, 0x41, 0, 1, 20, 4)
    struct.pack_into("<I", data, 384, 0x42)
    return data


class CDFLRPointerTableTests(unittest.TestCase):
    def inspect(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(data)
            return inspect_pointer_table(path)

    def test_valid_three_pointer_table(self):
        data = image()
        report = self.inspect(data)
        self.assertEqual(report["table_entries"], 3)
        self.assertEqual(report["table_bytes"], 12)
        self.assertEqual(report["zero_padding_bytes"], 244)
        self.assertEqual(report["base_address_candidate"], "0x80183000")
        self.assertEqual(report["first_target_file_offset"], 256)
        self.assertEqual(report["last_target_file_offset"], 384)
        self.assertEqual(report["target_first_word_0x41_indices"], [0, 1])
        self.assertEqual(report["target_first_word_0x41_count"], 2)
        self.assertEqual(report["type_0x41_span_rule_candidate_count"], 2)
        self.assertEqual(report["type_0x41_header_pattern_matches"], 2)
        self.assertEqual(report["type_0x41_span_rule_matches"], 2)
        self.assertEqual(report["type_0x41_span_rule_fail_indices"], [])
        self.assertEqual(report["source_sha256"], hashlib.sha256(data).hexdigest())
        self.assertFalse(report["interpretation"]["payload_bytes_emitted"])

    def test_wrong_type_0x41_length_does_not_pass_span_rule(self):
        data = image()
        struct.pack_into("<I", data, 256 + 12, 24)
        report = self.inspect(data)
        self.assertEqual(report["type_0x41_span_rule_candidate_count"], 2)
        self.assertEqual(report["type_0x41_header_pattern_matches"], 2)
        self.assertEqual(report["type_0x41_span_rule_matches"], 1)
        self.assertEqual(report["type_0x41_span_rule_fail_indices"], [0])

    def test_optional_native_exe_literal_correspondence(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            resource = folder / "CDFLR.BIN"
            resource.write_bytes(image())
            exe = bytearray(0x900)
            exe[:8] = b"PS-X EXE"
            struct.pack_into("<I", exe, 0x1C, 0x100)
            struct.pack_into("<I", exe, 0x810, 0x80183000)
            exe_path = folder / "WILDARMS.EXE"
            exe_path.write_bytes(exe)
            report = inspect_pointer_table(resource, exe_path)
        check = report["independent_executable_literal_check"]
        self.assertEqual(check["aligned_literal_match_count"], 1)
        self.assertEqual(check["aligned_literal_file_offsets"], [0x810])
        self.assertTrue(check["loader_relationship_not_proven"])

    def test_rejects_non_psx_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            resource = folder / "CDFLR.BIN"
            resource.write_bytes(image())
            exe = folder / "fake.exe"
            exe.write_bytes(bytes(0x900))
            with self.assertRaisesRegex(ValueError, "PS-X EXE"):
                inspect_pointer_table(resource, exe)

    def test_rejects_nonzero_bytes_after_sentinel(self):
        data = image()
        struct.pack_into("<I", data, 12, 1)
        with self.assertRaisesRegex(ValueError, "zero terminator|nonzero bytes"):
            self.inspect(data)

    def test_rejects_unsorted_pointers(self):
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            self.inspect(image((0x80183100, 0x80183180, 0x80183140)))

    def test_rejects_unaligned_pointers(self):
        with self.assertRaisesRegex(ValueError, "word-aligned"):
            self.inspect(image((0x80183100, 0x80183141, 0x80183180)))

    def test_rejects_target_outside_file(self):
        with self.assertRaisesRegex(ValueError, "outside the file"):
            self.inspect(image((0x80183100, 0x80183140, 0x80190000)))

    def test_rejects_short_image(self):
        with self.assertRaisesRegex(ValueError, "too small"):
            self.inspect(bytes(256))

    def test_rejects_missing_ram_words(self):
        with self.assertRaisesRegex(ValueError, "no candidate"):
            self.inspect(bytes(2048))


if __name__ == "__main__":
    unittest.main()
