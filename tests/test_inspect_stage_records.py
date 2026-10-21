"""Synthetic-only tests for private CDSTG stride metadata inspection."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from inspect_stage_records import inspect_records  # noqa: E402


class StageRecordProbeTests(unittest.TestCase):
    def test_four_synthetic_slots_one_marker_exception(self):
        stride = 128
        blocks = []
        for index in range(4):
            record = bytearray(stride)
            record[0:4] = (0x80150000 + index * 4).to_bytes(4, "little")
            record[8:12] = (0x8014F040).to_bytes(4, "little")
            if index != 2:
                record[60:64] = b"Sony"
            blocks.append(bytes(record))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(b"".join(blocks))
            report = inspect_records(path, stride, b"Sony", 60)
        self.assertEqual(report["record_count"], 4)
        self.assertEqual(report["marker_matches"], 3)
        self.assertEqual(report["marker_exceptions"], [2])
        self.assertEqual(report["unique_record_hash_count"], 4)
        self.assertEqual(report["word0_ram_like_count"], 4)
        self.assertEqual(report["word8_ram_like_count"], 4)
        self.assertEqual(report["records"][0]["sha256"], hashlib.sha256(blocks[0]).hexdigest())
        self.assertFalse(report["interpretation"]["copyrighted_payload_emitted"])

    def test_rejects_invalid_stride_or_incomplete_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(bytes(129))
            with self.assertRaisesRegex(ValueError, "whole number"):
                inspect_records(path, 128)
            with self.assertRaisesRegex(ValueError, ">= 64"):
                inspect_records(path, 0)

    def test_rejects_marker_out_of_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(bytes(128))
            with self.assertRaisesRegex(ValueError, "outside"):
                inspect_records(path, 128, b"Sony", 126)

    def test_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "nonempty"):
                inspect_records(path, 128)


if __name__ == "__main__":
    unittest.main()
