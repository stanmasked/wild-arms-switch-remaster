"""Synthetic-only tests for the bounded Mode 2/2352 ISO file extractor."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from extract_wild_arms_iso_files import (  # noqa: E402
    SECTOR_BYTES,
    SYNC,
    extract_entry,
)


def make_sector(payload=b"", mode=2, submode=0, duplicate=True, sync=True):
    sector = bytearray(SECTOR_BYTES)
    if sync:
        sector[:12] = SYNC
    sector[12:16] = bytes((0, 0, 0, mode))
    subheader = bytes((1, 0, submode, 0))
    sector[16:20] = subheader
    sector[20:24] = subheader if duplicate else bytes((1, 0, submode ^ 1, 0))
    sector[24:24 + min(len(payload), 2048)] = payload[:2048]
    return bytes(sector)


class ExtractWildArmsIsoFilesTests(unittest.TestCase):
    def _source(self, folder, sectors):
        path = Path(folder) / "synthetic.bin"
        path.write_bytes(b"".join(sectors))
        return path

    def test_extracts_payload_and_reports_hash_for_multisector_file(self):
        first_payload = bytes((i % 251 for i in range(2048)))
        second_payload = b"last three bytes plus padding"
        expected = first_payload + second_payload[:3]
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector(first_payload), make_sector(second_payload)])
            target = Path(folder) / "out" / "TEST.BIN"
            report = extract_entry(source, target, lba=0, size_bytes=len(expected))
            self.assertEqual(target.read_bytes(), expected)
        self.assertEqual(report["size_bytes"], len(expected))
        self.assertEqual(report["sectors_validated"], 2)
        self.assertEqual(report["sha256"], hashlib.sha256(expected).hexdigest())

    def test_rejects_invalid_sync(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector(sync=False)])
            target = Path(folder) / "out.bin"
            with self.assertRaisesRegex(ValueError, "sync pattern"):
                extract_entry(source, target, 0, 1)
            self.assertFalse(target.exists())

    def test_rejects_non_mode2_sector(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector(mode=1)])
            with self.assertRaisesRegex(ValueError, "Mode 2"):
                extract_entry(source, Path(folder) / "out.bin", 0, 1)

    def test_rejects_mismatched_duplicated_subheader(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector(duplicate=False)])
            with self.assertRaisesRegex(ValueError, "subheader mismatch"):
                extract_entry(source, Path(folder) / "out.bin", 0, 1)

    def test_rejects_form2_sector(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector(submode=0x20)])
            with self.assertRaisesRegex(ValueError, "Form 2"):
                extract_entry(source, Path(folder) / "out.bin", 0, 1)

    def test_rejects_extent_outside_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector()])
            with self.assertRaisesRegex(ValueError, "bounds"):
                extract_entry(source, Path(folder) / "out.bin", 1, 1)

    def test_failure_does_not_leave_partial_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector(), make_sector(sync=False)])
            output_dir = Path(folder) / "out"
            target = output_dir / "out.bin"
            with self.assertRaisesRegex(ValueError, "sync pattern"):
                extract_entry(source, target, 0, 2049)
            self.assertFalse(target.exists())
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self._source(folder, [make_sector()])
            target = Path(folder) / "out.bin"
            target.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                extract_entry(source, target, 0, 1)
            self.assertEqual(target.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
