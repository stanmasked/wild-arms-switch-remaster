"""Synthetic-only tests of transfer callers and dynamic-slot safeguards."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_wild_arms_transfer_families import inspect_call_families  # noqa: E402


def lui(dest, imm):
    return (15 << 26) | (dest << 16) | imm


def lw(dest, base, offset):
    return (35 << 26) | (base << 21) | (dest << 16) | offset


def sw(src, base, offset):
    return (43 << 26) | (base << 21) | (src << 16) | offset


def jal(address):
    return (3 << 26) | ((address >> 2) & 0x3FFFFFF)


def lhu(dest, base, offset):
    return (37 << 26) | (base << 21) | (dest << 16) | offset


def fixture():
    base, length = 0x80020000, 0x4000
    data = bytearray(0x800 + length)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<II", data, 0x18, base, length)
    for offset, slot in [(0x110, 0x2EA0), (0x150, 0x2EB8), (0x190, None)]:
        if slot is not None:
            struct.pack_into("<II", data, 0x800 + offset - 8,
                             lui(4, 0x800D), lw(4, 4, slot))
        struct.pack_into("<I", data, 0x800 + offset, jal(0x8002356C))
    callee_offset = 0x800 + 0x8002356C - base
    struct.pack_into("<I", data, callee_offset + 0x84, lhu(2, 4, 0))
    return data


def inspect(blob):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.exe"
        path.write_bytes(blob)
        return inspect_call_families(path)


class TransferCallFamilyTests(unittest.TestCase):
    def test_related_call_sites_and_halfword_read(self):
        result = inspect(fixture())
        self.assertEqual(result["call_site_count"], 3)
        self.assertEqual(result["calls_without_candidate_nearby_slot"], 1)
        self.assertEqual(result["nearby_slot_call_families"], [
            {"slot": "0x800D2EA0", "call_site_count": 1},
            {"slot": "0x800D2EB8", "call_site_count": 1},
        ])
        self.assertEqual(result["direct_adjacent_lui_lw_source_slot_reads"], [0x90C])
        self.assertEqual(result["direct_adjacent_lui_store_source_slot_writes"], [])
        self.assertEqual(result["callee_a0_halfword_read_sites"], [0x800 + 0x356C + 0x84])
        self.assertTrue(result["interpretation"]["no_original_bytes_emitted"])

    def test_matching_direct_store_is_detected(self):
        blob = fixture()
        struct.pack_into("<II", blob, 0x9C0, lui(4, 0x800D), sw(3, 4, 0x2EA0))
        result = inspect(blob)
        self.assertEqual(result["direct_adjacent_lui_store_source_slot_writes"], [0x9C4])
        self.assertEqual(result["all_store_immediate_0x2ea0_sites"], [0x9C4])

    def test_low_offset_without_matching_lui_is_not_resolved(self):
        blob = fixture()
        struct.pack_into("<II", blob, 0x9C0, lui(4, 0x800C), sw(3, 4, 0x2EA0))
        result = inspect(blob)
        self.assertEqual(result["direct_adjacent_lui_store_source_slot_writes"], [])
        self.assertEqual(result["all_store_immediate_0x2ea0_sites"], [0x9C4])

    def test_nearby_load_without_matching_lui_is_not_a_family(self):
        blob = fixture()
        struct.pack_into("<I", blob, 0x908, lui(4, 0x800C))
        result = inspect(blob)
        self.assertEqual(result["nearby_slot_call_families"], [
            {"slot": "0x800D2EB8", "call_site_count": 1}
        ])
        self.assertEqual(result["calls_without_candidate_nearby_slot"], 2)

    def test_invalid_header_and_declared_text_rejected(self):
        data = fixture()
        data[:8] = bytes(8)
        with self.assertRaisesRegex(ValueError, "magic"):
            inspect(data)
        data = fixture()
        struct.pack_into("<I", data, 0x1C, 0x8000)
        with self.assertRaisesRegex(ValueError, "text extent"):
            inspect(data)

    def test_wrong_callee_is_not_a_match(self):
        data = fixture()
        struct.pack_into("<I", data, 0x990, jal(0x80023570))
        self.assertEqual(inspect(data)["call_site_count"], 2)


if __name__ == "__main__":
    unittest.main()
