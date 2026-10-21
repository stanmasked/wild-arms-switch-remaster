"""Synthetic-only tests for bounded local container metadata probing."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from probe_container import MAX_SAMPLE_BYTES, probe  # noqa: E402


class ProbeContainerTests(unittest.TestCase):
    def test_reports_hash_and_bounded_sample_without_payload(self):
        data = bytearray(8192)
        # Repeated in-range little-endian values are hypotheses, not decoded offsets.
        data[0:4] = (0x100).to_bytes(4, "little")
        data[-8:-4] = (0x100).to_bytes(4, "little")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(data)
            result = probe(path, sample_bytes=64)
        self.assertEqual(result["file_size_bytes"], len(data))
        self.assertEqual(result["sample"]["bytes_read"], 64)
        self.assertEqual(result["sample"]["limit_bytes"], 64)
        self.assertEqual(result["sample"]["windows"][0]["offset"], 0)
        self.assertEqual(result["sample"]["windows"][-1]["offset"], len(data) - 8)
        self.assertLessEqual(result["sample"]["bytes_read"], 64)
        self.assertEqual(result["pointer_like_words"][0], {"value": 0x100, "count": 2})
        self.assertTrue(result["interpretation"]["payload_bytes_emitted"] is False)
        self.assertFalse(result["interpretation"]["complete_file_loaded_into_memory"])
        self.assertNotIn("raw_bytes", result)
        self.assertNotIn("sample_data", result)
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())

    def test_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty.bin"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                probe(path)

    def test_rejects_unbounded_sample_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidate.bin"
            path.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "sample_bytes"):
                probe(path, MAX_SAMPLE_BYTES + 1)

    def test_zero_heavy_sample_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "zero.bin"
            path.write_bytes(b"\x00" * 128 + b"\xff" * 128)
            result = probe(path, sample_bytes=256)
        self.assertEqual(result["sample"]["zero_byte_fraction"], 0.5)
        self.assertEqual(result["sample"]["shannon_entropy_bits_per_byte"], 1.0)


if __name__ == "__main__":
    unittest.main()
