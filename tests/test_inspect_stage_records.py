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
        stride = 4096
        blocks = []
        for index in range(4):
            record = bytearray(stride)
            record[0:4] = (0x80150010 + index * 4).to_bytes(4, "little")
            record[8:12] = (0x80150000).to_bytes(4, "little")
            record[12:16] = (2048).to_bytes(4, "little")
            record[32:36] = (0x801FFFF0).to_bytes(4, "little")
            entry_offset = 0x10 + index * 4
            stub = (
                0x3C1C8015,  # lui gp, 0x8015
                0x279C0020 + index * 4,  # addiu gp, gp, entry+16
                0x08000000 | ((0x80150000 >> 2) & 0x03FFFFFF),  # j load
                0,  # delay-slot nop
            )
            record[64 + entry_offset:64 + entry_offset + 16] = (
                b"".join(word.to_bytes(4, "little") for word in stub)
            )
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
        self.assertEqual(report["psx_exe_minus16_header_like_count"], 3)
        self.assertEqual(report["psx_exe_minus16_header_exceptions"], [2])
        self.assertEqual(report["psx_text_bytes_min"], 2048)
        self.assertEqual(report["psx_text_bytes_max"], 2048)
        self.assertEqual(report["mips_entry_stub_count"], 3)
        self.assertEqual(report["mips_gp_matches_entry_plus16_count"], 3)
        self.assertEqual(report["mips_jump_inside_text_count"], 3)
        self.assertEqual(report["records"][0]["sha256"], hashlib.sha256(blocks[0]).hexdigest())
        self.assertFalse(report["interpretation"]["copyrighted_payload_emitted"])

    def test_header_without_mips_stub_is_not_executable_evidence(self):
        record = bytearray(4096)
        record[0:4] = (0x80150010).to_bytes(4, "little")
        record[8:12] = (0x80150000).to_bytes(4, "little")
        record[12:16] = (2048).to_bytes(4, "little")
        record[32:36] = (0x801FFFF0).to_bytes(4, "little")
        record[60:64] = b"Sony"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(record)
            report = inspect_records(path, 4096)
        self.assertEqual(report["psx_exe_minus16_header_like_count"], 1)
        self.assertEqual(report["mips_entry_stub_count"], 0)
        self.assertEqual(report["mips_gp_matches_entry_plus16_count"], 0)
        self.assertEqual(report["mips_jump_inside_text_count"], 0)

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
