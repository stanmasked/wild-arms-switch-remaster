"""Synthetic-only verification of conservative PS-X EXE address calculation."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_wild_arms_slot_writes import audit_slot_writes  # noqa: E402


def lui(rt, hi):
    return (15 << 26) | (rt << 16) | hi


def ori(rt, rs, imm):
    return (13 << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def addiu(rt, rs, imm):
    return (9 << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def lw(rt, base, imm):
    return (35 << 26) | (base << 21) | (rt << 16) | (imm & 65535)


def sw(rt, base, imm):
    return (43 << 26) | (base << 21) | (rt << 16) | (imm & 65535)


def sh(rt, base, imm):
    return (41 << 26) | (base << 21) | (rt << 16) | (imm & 65535)


def addu(rd, rs, rt):
    return (rs << 21) | (rt << 16) | (rd << 11) | 33


def beq(rs, rt, rel):
    return (4 << 26) | (rs << 21) | (rt << 16) | (rel & 65535)


def fixture(instructions):
    text_size = max(128, ((len(instructions) * 4 + 3) // 4) * 4)
    data = bytearray(0x800 + text_size)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<II", data, 0x18, 0x80011420, text_size)
    for i, instruction in enumerate(instructions):
        struct.pack_into("<I", data, 0x800 + 4 * i, instruction)
    return data


def audit(data):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.exe"
        path.write_bytes(data)
        return audit_slot_writes(path)


class SlotWritesTests(unittest.TestCase):
    def test_lui_ori_addiu_and_stores_are_recognized(self):
        report = audit(fixture([
            lui(8, 0x800D), ori(8, 8, 0x2E00), addiu(8, 8, 0xA0),
            sw(2, 8, 0), sh(2, 8, 0),
        ]))
        self.assertEqual(report["computed_constant_target_store_count"], 2)
        self.assertEqual([x["operation"] for x in report["computed_constant_target_store_sites"]], ["SW", "SH"])
        self.assertEqual([x["file_offset"] for x in report["computed_constant_target_store_sites"]], [0x80C, 0x810])

    def test_register_addition_with_adjusted_displacement(self):
        report = audit(fixture([
            lui(8, 0x800D), ori(8, 8, 0x2E9C),
            addiu(9, 0, 4), addu(8, 8, 9), sw(3, 8, 0),
        ]))
        self.assertEqual(report["computed_constant_target_store_count"], 1)
        self.assertEqual(report["computed_constant_target_store_sites"][0]["file_offset"], 0x810)

    def test_branch_and_delay_slot_prevent_false_proof(self):
        report = audit(fixture([
            lui(8, 0x800D), ori(8, 8, 0x2EA0), beq(0, 0, 1),
            sw(3, 8, 0), sw(3, 8, 0),
        ]))
        self.assertEqual(report["computed_constant_target_store_count"], 0)
        self.assertTrue(report["interpretation"]["control_transfer_delay_slots_not_audited"])

    def test_runtime_load_clobbers_symbolic_register(self):
        report = audit(fixture([
            lui(8, 0x800D), ori(8, 8, 0x2EA0), lw(8, 9, 0), sw(3, 8, 0),
        ]))
        self.assertEqual(report["computed_constant_target_store_count"], 0)

    def test_unknown_base_and_low_immediate_are_not_proof(self):
        report = audit(fixture([sw(3, 8, 0x2EA0)]))
        self.assertEqual(report["computed_constant_target_store_count"], 0)
        self.assertEqual(report["unknown_base_same_low_immediate_sites"], [0x800])

    def test_bad_header_and_declared_text_fail_closed(self):
        data = fixture([sw(3, 8, 0)])
        data[:8] = b"BAD-EXE!"
        with self.assertRaisesRegex(ValueError, "magic"):
            audit(data)
        data = fixture([sw(3, 8, 0)])
        struct.pack_into("<I", data, 0x1C, 0x100000)
        with self.assertRaisesRegex(ValueError, "declared text"):
            audit(data)

    def test_zero_register_is_immutable(self):
        report = audit(fixture([
            lui(0, 0x800D), ori(0, 0, 0x2EA0), sw(1, 0, 0),
        ]))
        self.assertEqual(report["computed_constant_target_store_count"], 0)


if __name__ == "__main__":
    unittest.main()
