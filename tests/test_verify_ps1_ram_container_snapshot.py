"""Synthetic-only tests of PS1 RAM-to-container snapshot equivalence."""
import hashlib
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_ps1_ram_container_snapshot import (  # noqa: E402
    DEFAULT_ADDRESS, RAM_BYTES, compare_private_ram
)


class PrivateRamSnapshotTests(unittest.TestCase):
    def run_fixture(self, *, mismatches=(), container_offset=0, address=DEFAULT_ADDRESS,
                    compare_bytes=8192, ram_length=RAM_BYTES, source_length=None):
        source = bytes((i % 251 for i in range(source_length or container_offset + compare_bytes + 64)))
        memory = bytearray(ram_length)
        physical = address & (RAM_BYTES - 1)
        if physical + compare_bytes <= len(memory):
            segment = source[container_offset:container_offset + compare_bytes]
            memory[physical:physical + compare_bytes] = (
                segment + bytes(compare_bytes - len(segment))
            )
        for index in mismatches:
            memory[physical + index] ^= 0xFF
        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "CDFLR.BIN"
            ram = Path(folder) / "ram.bin"
            container.write_bytes(source)
            ram.write_bytes(memory)
            result = compare_private_ram(container, ram, address=address,
                                         compare_bytes=compare_bytes,
                                         container_offset=container_offset)
        return result, source

    def test_exact_match_to_private_container_slice(self):
        result, source = self.run_fixture()
        self.assertEqual(result["comparison_status"], "EXACT_MATCH")
        self.assertEqual(result["matching_window_count"], 4)
        self.assertEqual(result["matching_prefix_bytes"], 8192)
        self.assertEqual(result["different_byte_count"], 0)
        self.assertIsNone(result["first_difference_offset_in_slice"])
        self.assertEqual(result["container_slice_sha256"],
                         hashlib.sha256(source[:8192]).hexdigest())
        self.assertEqual(result["ram_slice_sha256"], result["container_slice_sha256"])
        self.assertFalse(result["interpretation"]["original_content_bytes_emitted"])

    def test_single_mutation_is_not_misclassified_as_matching(self):
        result, _ = self.run_fixture(mismatches=[2091])
        self.assertEqual(result["comparison_status"], "NOT_IDENTICAL_AT_SNAPSHOT")
        self.assertEqual(result["matching_window_count"], 3)
        self.assertEqual(result["first_difference_offset_in_slice"], 2091)
        self.assertEqual(result["matching_prefix_bytes"], 2091)
        self.assertEqual(result["different_byte_count"], 1)
        self.assertTrue(result["interpretation"]["mismatch_does_not_exclude_prior_load_and_mutation"])

    def test_two_mutations_in_one_window_count_bytes_correctly(self):
        result, _ = self.run_fixture(mismatches=[0, 1023])
        self.assertEqual(result["matching_window_count"], 3)
        self.assertEqual(result["first_difference_offset_in_slice"], 0)
        self.assertEqual(result["different_byte_count"], 2)

    def test_kseg1_alias_uses_same_physical_ram_location(self):
        result, _ = self.run_fixture(address=0xA0183000)
        self.assertEqual(result["comparison_status"], "EXACT_MATCH")
        self.assertEqual(result["ram_physical_offset"], 0x183000)

    def test_source_offset_and_partial_last_window(self):
        result, source = self.run_fixture(container_offset=128, compare_bytes=5001)
        self.assertEqual(result["window_count"], 3)
        self.assertEqual(result["matching_window_count"], 3)
        self.assertEqual(result["source_file_offset"], 128)
        self.assertEqual(result["container_slice_sha256"],
                         hashlib.sha256(source[128:5129]).hexdigest())

    def test_wrong_ram_length_rejected(self):
        with self.assertRaisesRegex(ValueError, "2,097,152"):
            self.run_fixture(ram_length=RAM_BYTES - 1)

    def test_container_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, "container bounds"):
            self.run_fixture(compare_bytes=8192, source_length=100)

    def test_unknown_address_segment_rejected(self):
        with self.assertRaisesRegex(ValueError, "KSEG0/KSEG1"):
            self.run_fixture(address=0x00183000)

    def test_invalid_window_budget_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            ram = Path(folder) / "ram"
            source.write_bytes(b"x" * 16)
            ram.write_bytes(bytes(RAM_BYTES))
            with self.assertRaisesRegex(ValueError, "1..65536"):
                compare_private_ram(source, ram, compare_bytes=8, window_bytes=0)


if __name__ == "__main__":
    unittest.main()
