"""Synthetic-only checks of candidate trimmed executable record scans."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_wild_arms_cdstg_overlay_writes import audit_overlays  # noqa: E402


def lui(rt, imm):
    return (15 << 26) | (rt << 16) | (imm & 65535)


def ori(rt, rs, imm):
    return (13 << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def sw(rt, rs, imm):
    return (43 << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def beq(rs, rt, rel):
    return (4 << 26) | (rs << 21) | (rt << 16) | (rel & 65535)


def fixture(modify=None):
    stride = 1024
    records = []
    for index in range(3):
        record = bytearray(stride)
        if index != 1:
            struct.pack_into("<4I", record, 0, 0x80150010, 0, 0x80150000, 256)
            struct.pack_into("<I", record, 0x20, 0x801FFFF0)
            record[0x3C:0x40] = b"Sony"
        if index == 0:
            struct.pack_into("<3I", record, 0x40,
                             lui(8, 0x800D), ori(8, 8, 0x2EA0), sw(3, 8, 0))
        if modify:
            modify(index, record)
        records.append(record)
    return b"".join(records)


def inspect(contents):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.bin"
        path.write_bytes(contents)
        return audit_overlays(path, record_bytes=1024, expected_records=3)


class OverlayWritersTests(unittest.TestCase):
    def test_valid_overlay_store_and_separate_exception(self):
        result = inspect(fixture())
        self.assertEqual(result["psx_overlay_like_records_scanned"], 2)
        self.assertEqual(result["exceptional_record_indices"], [1])
        self.assertEqual(result["constant_proven_store_site_count"], 1)
        self.assertEqual(result["constant_proven_store_sites"][0], {
            "record_index": 0, "offset_in_record": 0x48, "operation": "SW"
        })
        self.assertFalse(result["interpretation"]["original_asset_bytes_emitted"])

    def test_branch_delay_slot_is_not_certified(self):
        def modify(index, record):
            if index == 0:
                struct.pack_into("<5I", record, 0x40,
                                 lui(8, 0x800D), ori(8, 8, 0x2EA0),
                                 beq(0, 0, 1), sw(3, 8, 0), sw(3, 8, 0))
        result = inspect(fixture(modify))
        self.assertEqual(result["constant_proven_store_site_count"], 0)
        self.assertEqual(result["exceptional_record_indices"], [1])

    def test_malformed_header_is_skipped_not_decoded(self):
        def modify(index, record):
            if index == 2:
                struct.pack_into("<I", record, 0x20, 0)
        result = inspect(fixture(modify))
        self.assertEqual(result["psx_overlay_like_records_scanned"], 1)
        self.assertEqual(result["exceptional_record_indices"], [1, 2])

    def test_rejects_incomplete_or_unaligned_geometry(self):
        with self.assertRaisesRegex(ValueError, "geometry"):
            inspect(fixture()[:-1])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.bin"
            path.write_bytes(fixture())
            with self.assertRaisesRegex(ValueError, "record_bytes"):
                audit_overlays(path, record_bytes=65, expected_records=3)
            with self.assertRaisesRegex(ValueError, "expected_records"):
                audit_overlays(path, record_bytes=1024, expected_records=0)


if __name__ == "__main__":
    unittest.main()
