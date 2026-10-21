"""Synthetic-only tests for shared PS-X EXE transfer-call provenance."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_wild_arms_transfer_calls import audit_transfer_calls  # noqa: E402


def lui(rt, imm):
    return (15 << 26) | (rt << 16) | imm


def ori(rt, rs, imm):
    return (13 << 26) | (rs << 21) | (rt << 16) | imm


def lw(rt, rs, imm):
    return (35 << 26) | (rs << 21) | (rt << 16) | imm


def jal(addr):
    return (3 << 26) | ((addr >> 2) & 0x03ffffff)


def fixture():
    data = bytearray(0x800 + 0x200)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<II", data, 0x18, 0x80011420, 0x200)
    call = [
        lui(5, 0x8018), ori(5, 5, 0x3000), lui(6, 3),
        lui(4, 0x800d), lw(4, 4, 0x2ea0),
        jal(0x8002356c), ori(6, 6, 0xa000),
    ]
    struct.pack_into("<7I", data, 0x820, *call)
    struct.pack_into("<I", data, 0x8c0, jal(0x8002356c))
    return data


def inspect(contents, target=0x8002356c):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.exe"
        path.write_bytes(contents)
        return audit_transfer_calls(path, target)


class TransferProvenanceTests(unittest.TestCase):
    def test_shared_callee_and_dynamic_pointer_slot(self):
        report = inspect(fixture())
        self.assertEqual(report["call_site_count"], 2)
        self.assertEqual(report["matching_candidate_buffer_call_count"], 1)
        self.assertEqual(report["matching_candidate_buffer_call_offsets"], [0x834])
        self.assertEqual(report["direct_lui_lw_source_slot_read_offsets"], [0x830])
        self.assertEqual(report["source_pointer_slot_distance_after_text"],
                         0x800d2ea0 - (0x80011420 + 0x200))
        self.assertTrue(report["source_pointer_slot_outside_declared_text"])
        self.assertTrue(report["interpretation"]["file_selection_and_buffer_provenance_not_proven"])
        self.assertFalse(report["interpretation"]["proprietary_bytes_emitted"])

    def test_wrong_load_address_does_not_certify_special_call(self):
        data = fixture()
        struct.pack_into("<I", data, 0x830, lw(4, 4, 0x2ea4))
        report = inspect(data)
        self.assertEqual(report["call_site_count"], 2)
        self.assertEqual(report["matching_candidate_buffer_call_count"], 0)
        self.assertEqual(report["direct_lui_lw_source_slot_read_count"], 0)

    def test_wrong_length_delay_slot_rejected(self):
        data = fixture()
        struct.pack_into("<I", data, 0x838, ori(6, 6, 0xb000))
        report = inspect(data)
        self.assertEqual(report["call_site_count"], 2)
        self.assertEqual(report["matching_candidate_buffer_call_count"], 0)

    def test_rejects_invalid_magic_and_bounded_text(self):
        data = fixture()
        data[:8] = bytes(8)
        with self.assertRaisesRegex(ValueError, "magic"):
            inspect(data)
        data = fixture()
        struct.pack_into("<I", data, 0x1c, 0x400)
        with self.assertRaisesRegex(ValueError, "text range"):
            inspect(data)

    def test_nonmatching_callee_has_zero_calls(self):
        self.assertEqual(inspect(fixture(), 0x80023570)["call_site_count"], 0)
        self.assertEqual(inspect(fixture())["call_site_count"], 2)


if __name__ == "__main__":
    unittest.main()
