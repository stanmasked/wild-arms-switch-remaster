"""Synthetic-only tests for the read-only ISO9660 MODE2/Form1 inventory."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from inspect_disc import inspect  # noqa: E402

SECTOR_BYTES = 2352
BLOCK_BYTES = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def put_both(data, offset, value, width):
    data[offset:offset + width] = value.to_bytes(width, "little")
    data[offset + width:offset + 2 * width] = value.to_bytes(width, "big")


def iso_record(identifier, lba, size, directory=False):
    padding = 1 if len(identifier) % 2 == 0 else 0
    length = 33 + len(identifier) + padding
    record = bytearray(length)
    record[0] = length
    record[1] = 0
    put_both(record, 2, lba, 4)
    put_both(record, 10, size, 4)
    record[25] = 2 if directory else 0
    put_both(record, 28, 1, 2)
    record[32] = len(identifier)
    record[33:33 + len(identifier)] = identifier
    return record


def sector(user_data, submode=0x08):
    raw = bytearray(SECTOR_BYTES)
    raw[:12] = SYNC
    raw[12:16] = bytes((0, 0, 0, 2))
    raw[15] = 2
    subheader = bytes((0, 0, submode, 0))
    raw[16:20] = subheader
    raw[20:24] = subheader
    raw[24:24 + BLOCK_BYTES] = user_data
    return raw


def sample_disc():
    image = bytearray(24 * SECTOR_BYTES)
    pvd = bytearray(BLOCK_BYTES)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[40:72] = b"TESTVOL".ljust(32, b" ")
    put_both(pvd, 80, 24, 4)
    put_both(pvd, 128, BLOCK_BYTES, 2)
    root = iso_record(b"\x00", 20, BLOCK_BYTES, directory=True)
    pvd[156:156 + len(root)] = root

    directory = bytearray(BLOCK_BYTES)
    records = (
        iso_record(b"\x00", 20, BLOCK_BYTES, directory=True)
        + iso_record(b"\x01", 20, BLOCK_BYTES, directory=True)
        + iso_record(b"TEST.BIN;1", 21, 4)
    )
    directory[:len(records)] = records
    image[16 * SECTOR_BYTES:17 * SECTOR_BYTES] = sector(pvd)
    image[20 * SECTOR_BYTES:21 * SECTOR_BYTES] = sector(directory)
    return image


def inspect_image(image):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "sample.bin"
        path.write_bytes(image)
        return inspect(path)


class InspectDiscTests(unittest.TestCase):
    def test_valid_synthetic_volume_reports_metadata_only(self):
        result = inspect_image(sample_disc())
        self.assertEqual(result["volume"], "TESTVOL")
        self.assertEqual(result["entries"], [{
            "lba": 21, "size": 4, "directory": False, "path": "/TEST.BIN;1",
        }])

    def test_rejects_non_sector_aligned_raw_image(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            inspect_image(sample_disc() + b"x")

    def test_rejects_image_without_pvd_sector(self):
        with self.assertRaisesRegex(ValueError, "too short"):
            inspect_image(bytes(16 * SECTOR_BYTES))

    def test_rejects_bad_sync(self):
        image = sample_disc()
        image[16 * SECTOR_BYTES] = 1
        with self.assertRaisesRegex(ValueError, "sync"):
            inspect_image(image)

    def test_rejects_non_mode2_pvd(self):
        image = sample_disc()
        image[16 * SECTOR_BYTES + 15] = 1
        with self.assertRaisesRegex(ValueError, "Not MODE2"):
            inspect_image(image)

    def test_rejects_mode2_form2_pvd(self):
        image = sample_disc()
        image[16 * SECTOR_BYTES + 18] |= 0x20
        image[16 * SECTOR_BYTES + 22] |= 0x20
        with self.assertRaisesRegex(ValueError, "Form1"):
            inspect_image(image)

    def test_rejects_duplicate_xa_subheader_mismatch(self):
        image = sample_disc()
        image[16 * SECTOR_BYTES + 20] ^= 1
        with self.assertRaisesRegex(ValueError, "subheader"):
            inspect_image(image)

    def test_rejects_pvd_endian_mismatch(self):
        image = sample_disc()
        image[16 * SECTOR_BYTES + 24 + 156 + 6] = 21
        with self.assertRaisesRegex(ValueError, "extent LBA endian"):
            inspect_image(image)

    def test_rejects_short_directory_record(self):
        image = sample_disc()
        image[20 * SECTOR_BYTES + 24] = 33
        with self.assertRaisesRegex(ValueError, "shorter than 34"):
            inspect_image(image)

    def test_rejects_mismatched_file_size_endian_copies(self):
        image = sample_disc()
        record = 20 * SECTOR_BYTES + 24 + 68
        image[record + 14:record + 18] = (5).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "data length endian"):
            inspect_image(image)

    def test_rejects_extent_outside_iso_volume(self):
        image = sample_disc()
        record = 20 * SECTOR_BYTES + 24 + 68
        put_both(image, record + 2, 23, 4)
        put_both(image, record + 10, 4096, 4)
        with self.assertRaisesRegex(ValueError, "extent exceeds"):
            inspect_image(image)

    def test_rejects_interleaved_extents(self):
        image = sample_disc()
        record = 20 * SECTOR_BYTES + 24 + 68
        image[record + 26] = 1
        with self.assertRaisesRegex(ValueError, "interleaved"):
            inspect_image(image)

    def test_rejects_directory_record_crossing_block_boundary(self):
        image = sample_disc()
        directory = bytearray(BLOCK_BYTES)
        prefix = (
            iso_record(b"\x00", 20, BLOCK_BYTES, directory=True)
            + iso_record(b"\x01", 20, BLOCK_BYTES, directory=True)
            + b"".join(iso_record(b"A" * 221, 21, 0) for _ in range(7))
            + iso_record(b"B" * 135, 21, 0)
        )
        self.assertEqual(len(prefix), BLOCK_BYTES - 34)
        directory[:len(prefix)] = prefix
        directory[len(prefix)] = 35
        image[20 * SECTOR_BYTES:21 * SECTOR_BYTES] = sector(directory)
        with self.assertRaisesRegex(ValueError, "crosses a logical block"):
            inspect_image(image)


if __name__ == "__main__":
    unittest.main()
