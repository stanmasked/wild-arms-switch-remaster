"""Synthetic-only MIPS checks for proposed CDFLR RAM buffer patterns."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdflr_loader_code import audit_loader  # noqa: E402


def lui(rt, imm):
    return (15 << 26) | (rt << 16) | imm


def ori(rt, rs, imm):
    return (13 << 26) | (rs << 21) | (rt << 16) | imm


def lw(rt, base, off):
    return (35 << 26) | (base << 21) | (rt << 16) | off


def sw(rt, base, off):
    return (43 << 26) | (base << 21) | (rt << 16) | off


def addiu(rt, rs, imm):
    return (9 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def bne(rs, rt, rel):
    return (5 << 26) | (rs << 21) | (rt << 16) | (rel & 0xFFFF)


def make_exe():
    data = bytearray(0x800 + 0x200)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<I", data, 0x18, 0x80011420)
    struct.pack_into("<I", data, 0x1C, 0x200)
    call = [
        lui(5, 0x8018), ori(5, 5, 0x3000), lui(6, 3),
        lui(4, 0x800D), lw(4, 4, 0x2EA0),
        (3 << 26) | ((0x8002356C >> 2) & 0x03FFFFFF),
        ori(6, 6, 0xA000),
    ]
    copy = [
        lui(7, 0x8018), ori(7, 7, 0x3000), lui(6, 0x8020),
        lui(8, 0x8023), ori(8, 8, 0xA000),
        *[lw(2 + i, 6, i * 4) for i in range(4)],
        *[sw(2 + i, 7, i * 4) for i in range(4)],
        addiu(6, 6, 16), bne(6, 8, -10), addiu(7, 7, 16),
    ]
    for offset, instructions in [(0x820, call), (0x880, copy)]:
        struct.pack_into("<" + str(len(instructions)) + "I",
                         data, offset, *instructions)
    return data


def inspect(data):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.exe"
        path.write_bytes(data)
        return audit_loader(path)


class LoaderPatternTests(unittest.TestCase):
    def test_two_code_constructors_call_and_bounded_copy(self):
        report = inspect(make_exe())
        self.assertEqual(report["base_lui_ori_constructor_offsets"], [0x820, 0x880])
        self.assertEqual(len(report["loader_argument_call_sites"]), 1)
        self.assertEqual(report["loader_argument_call_sites"][0]["size_argument_bytes"], 0x3A000)
        self.assertEqual(report["loader_argument_call_sites"][0]["call_target_address"], "0x8002356C")
        self.assertEqual(len(report["memory_copy_loops"]), 1)
        self.assertEqual(report["memory_copy_loops"][0]["copy_bytes"], 0x3A000)
        self.assertEqual(report["memory_copy_loops"][0]["loop_iterations"], 0x3A000 // 16)
        self.assertTrue(report["interpretation"]["relationship_to_named_cdflr_file_not_proven"])
        self.assertFalse(report["interpretation"]["proprietary_code_bytes_emitted"])

    def test_wrong_branch_target_blocks_copy_claim(self):
        exe = make_exe()
        struct.pack_into("<I", exe, 0x880 + 14 * 4, bne(6, 8, -9))
        report = inspect(exe)
        self.assertEqual(len(report["memory_copy_loops"]), 0)
        self.assertEqual(len(report["base_lui_ori_constructor_offsets"]), 2)

    def test_wrong_call_size_blocks_loader_call_claim(self):
        exe = make_exe()
        struct.pack_into("<I", exe, 0x820 + 6 * 4, ori(6, 6, 0x9000))
        report = inspect(exe)
        self.assertEqual(len(report["loader_argument_call_sites"]), 0)
        self.assertEqual(len(report["memory_copy_loops"]), 1)

    def test_invalid_executable_header(self):
        exe = make_exe()
        exe[:8] = bytes(8)
        with self.assertRaisesRegex(ValueError, "PS-X EXE"):
            inspect(exe)

    def test_text_extent_must_fit(self):
        exe = make_exe()
        struct.pack_into("<I", exe, 0x1C, 0x10000)
        with self.assertRaisesRegex(ValueError, "text extent"):
            inspect(exe)


if __name__ == "__main__":
    unittest.main()
