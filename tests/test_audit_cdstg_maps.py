"""Original-free synthetic checks of map and graphics pointer inventories."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdstg_maps import audit_cdstg_maps  # noqa: E402

STRIDE = 2048
GFX = 512
MB = 0x8014F000
GB = 0x80164000


def synthetic_map(index, *, corrupt=None):
    data = bytearray(STRIDE)
    if index == 1:
        data[:8] = b"DUMMY!!\0"
        data[512] = 73
        return bytes(data)
    struct.pack_into("<I", data, 8, MB + 0x40)
    ptr = [0] * 18
    ptr[0] = MB + 0x8C
    ptr[5] = MB + 0x90
    ptr[6] = MB + 0xA0
    ptr[7] = MB + 0xB0
    ptr[8] = MB + 0xB8 if index == 2 else 0
    ptr[14] = MB + 0xC0
    ptr[16] = MB + 0xD0
    ptr[17] = MB + 0xE0
    struct.pack_into("<18I", data, 0x40, *ptr)
    for position, offset in enumerate([0x100, 0x200, 0x300, 0x400]):
        struct.pack_into("<I", data, GFX + position * 4, GB + offset)
    data[GFX + 0x100] = index + 10
    if corrupt == "gfx_order":
        struct.pack_into("<I", data, GFX + 8, GB + 0x180)
    elif corrupt == "script_outside":
        struct.pack_into("<I", data, 0x40 + 6 * 4, MB + GFX)
    elif corrupt == "script_entries":
        struct.pack_into("<I", data, 0x40 + 6 * 4, MB + 0xB2)
    elif corrupt == "gfx_zero":
        struct.pack_into("<I", data, GFX + 0 * 4, 0)
    return bytes(data)


def scan(contents, *, exe=None):
    with tempfile.TemporaryDirectory() as td:
        source = Path(td) / "CDSTG.BIN"
        source.write_bytes(contents)
        if exe is not None:
            executable = Path(td) / "WILDARMS.EXE"
            executable.write_bytes(exe)
        else:
            executable = None
        return audit_cdstg_maps(source, map_bytes=STRIDE,
                                graphics_offset=GFX, map_count=3,
                                dummy_index=1, executable=executable,
                                include_names=exe is not None)


class OriginalMapIndexTests(unittest.TestCase):
    def test_map_index_covers_two_realistic_and_one_dummy(self):
        report = scan(synthetic_map(0) + synthetic_map(1) + synthetic_map(2))
        self.assertEqual(report["map_count"], 3)
        self.assertEqual(report["structurally_indexed_maps"], 2)
        self.assertEqual(report["dummy_map_indices"], [1])
        self.assertEqual(report["unique_full_graphics_region_sha256_count"], 3)
        self.assertEqual(report["candidate_graphics_pointer_count_histogram"], {"4": 2})
        self.assertEqual(report["maps"][0]["first_graphics_pointer_offset"], 256)
        self.assertEqual(report["maps"][0]["candidate_graphics_pointer_count"], 4)
        self.assertEqual(report["maps"][0]["global_script_entry_count"], 8)
        self.assertTrue(report["maps"][2]["has_script_2"])
        self.assertEqual(report["maps"][1]["status"], "DUMMY_UNCLASSIFIED")
        self.assertTrue(report["interpretation"]["original_source_bytes_emitted"] is False)

    def test_private_executable_name_binding(self):
        exe = bytearray(0x8100)
        exe[:8] = b"PS-X EXE"
        for idx, label in enumerate((b"Area Zero", b"", b"Surf Village")):
            location = 0x7800 + idx * 32
            pointer = MB - 0x3DC0 + location - 0x800  # = EXE_RAM_TEXT_BASE + location - 0x800
            pointer = 0x80011420 + location - 0x800
            struct.pack_into("<I", exe, 0x7578 + 4 * idx, pointer)
            exe[location:location + len(label) + 1] = label + b"\0"
        report = scan(synthetic_map(0) + synthetic_map(1) + synthetic_map(2),
                      exe=bytes(exe))
        self.assertEqual(report["maps"][0]["map_name_raw_private"], "Area Zero")
        self.assertEqual(report["maps"][2]["map_name_raw_private"], "Surf Village")
        self.assertEqual(report["maps"][1]["map_name_raw_private"], "")

    def test_bad_script_pointer_must_fail(self):
        with self.assertRaisesRegex(ValueError, "script table pointer"):
            scan(synthetic_map(0, corrupt="script_outside") +
                 synthetic_map(1) + synthetic_map(2))

    def test_bad_script_entry_table_must_fail(self):
        with self.assertRaisesRegex(ValueError, "script-entry"):
            scan(synthetic_map(0, corrupt="script_entries") +
                 synthetic_map(1) + synthetic_map(2))

    def test_graphics_pointer_out_of_order_must_fail(self):
        with self.assertRaisesRegex(ValueError, "graphics pointer run"):
            scan(synthetic_map(0, corrupt="gfx_order") +
                 synthetic_map(1) + synthetic_map(2))

    def test_missing_first_graphics_pointer_must_fail(self):
        with self.assertRaisesRegex(ValueError, "graphics pointer run"):
            scan(synthetic_map(0, corrupt="gfx_zero") +
                 synthetic_map(1) + synthetic_map(2))

    def test_partial_cd_stg_record_must_fail(self):
        with self.assertRaisesRegex(ValueError, "exact fixed-map geometry"):
            scan((synthetic_map(0) + synthetic_map(1) +
                  synthetic_map(2))[:-1])

    def test_invalid_geometry_parameters_must_fail(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "fake.bin"
            file.write_bytes(synthetic_map(0))
            with self.assertRaisesRegex(ValueError, "bounded map"):
                audit_cdstg_maps(file, map_bytes=4096,
                                 graphics_offset=4000,
                                 map_count=1, dummy_index=0)
            with self.assertRaisesRegex(ValueError, "dummy_index"):
                audit_cdstg_maps(file, map_bytes=2048,
                                 graphics_offset=512,
                                 map_count=1, dummy_index=25)

    def test_names_not_emitted_by_default(self):
        report = scan(synthetic_map(0) + synthetic_map(1) + synthetic_map(2))
        self.assertNotIn("map_name_raw_private", report["maps"][0])


if __name__ == "__main__":
    unittest.main()
