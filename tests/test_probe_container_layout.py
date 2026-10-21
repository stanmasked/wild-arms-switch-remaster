"""Synthetic-only tests for bounded, metadata-only container reconnaissance."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from probe_container_layout import probe  # noqa: E402

SECTOR_BYTES = 2352
BLOCK_BYTES = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
CANDIDATE = "/BIN/CDSTG.BIN;1"


def raw_sector(payload, submode=0x08, mode=2, valid_sync=True):
    raw = bytearray(SECTOR_BYTES)
    raw[:12] = SYNC if valid_sync else b"BAD" + bytes(9)
    raw[12:16] = bytes((0, 0, 0, mode))
    raw[15] = mode
    subheader = bytes((0, 0, submode, 0))
    raw[16:20] = subheader
    raw[20:24] = subheader
    raw[24:24 + BLOCK_BYTES] = payload
    return raw


def fixture(root, submode=0x08, mode=2, valid_sync=True, size=4096):
    root = Path(root)
    image_path = root / "private-disc.bin"
    inventory_path = root / "inventory.json"
    image = bytearray(24 * SECTOR_BYTES)
    payload_a = bytearray(BLOCK_BYTES)
    struct.pack_into("<III", payload_a, 0, 0x8015F624, 0, 0x8014F040)
    payload_b = bytearray((index % 251 for index in range(BLOCK_BYTES)))
    image[21 * SECTOR_BYTES:22 * SECTOR_BYTES] = raw_sector(
        payload_a, submode=submode, mode=mode, valid_sync=valid_sync)
    image[22 * SECTOR_BYTES:23 * SECTOR_BYTES] = raw_sector(payload_b)
    image_path.write_bytes(image)
    inventory_path.write_text(json.dumps({
        "volume": "TESTVOL",
        "entries": [{
            "path": CANDIDATE, "lba": 21, "size": size, "directory": False,
        }],
    }), encoding="utf-8")
    return image_path, inventory_path


class BoundedContainerProbeTests(unittest.TestCase):
    def test_reports_statistics_and_pointer_like_offsets_without_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder)
            result = probe(image, inventory, sample_bytes=4096)
            self.assertEqual(result["kind"], "BOUNDED_PRIVATE_CONTAINER_LAYOUT_PROBE")
            self.assertFalse(result["original_payload_exported"])
            self.assertFalse(result["decoded_assets_exported"])
            item = result["candidates"][0]
            self.assertEqual(item["status"], "SAMPLED")
            self.assertEqual(item["sampled_payload_bytes"], 4096)
            self.assertEqual(item["sampled_sector_count"], 2)
            self.assertEqual(item["word_summary"]["ps1_kseg0_pointer_like_word_count"], 2)
            self.assertEqual(item["word_summary"]["first_pointer_like_word_offsets"], [0, 8])
            self.assertEqual(len(item["sample_sha256"]), 64)
            self.assertNotIn("payload_hex", item)
            self.assertNotIn("raw_payload", item)

    def test_sample_is_bounded_by_declared_file_size(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder, size=100)
            result = probe(image, inventory, sample_bytes=4096)
            item = result["candidates"][0]
            self.assertEqual(item["sampled_payload_bytes"], 100)
            self.assertEqual(item["sampled_sector_count"], 1)

    def test_form2_fails_closed_without_payload_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder, submode=0x28)
            item = probe(image, inventory, sample_bytes=4096)["candidates"][0]
            self.assertEqual(item["status"], "UNSUPPORTED_MODE2_FORM2")
            self.assertNotIn("sample_sha256", item)
            self.assertNotIn("word_summary", item)

    def test_non_mode2_sector_is_reported_as_unsupported(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder, mode=1)
            item = probe(image, inventory, sample_bytes=4096)["candidates"][0]
            self.assertEqual(item["status"], "UNSUPPORTED_SECTOR_MODE")
            self.assertNotIn("sample_sha256", item)

    def test_bad_sector_sync_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder, valid_sync=False)
            with self.assertRaisesRegex(ValueError, "sector sync"):
                probe(image, inventory, sample_bytes=2048)

    def test_extent_outside_raw_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder)
            data = json.loads(inventory.read_text())
            data["entries"][0]["lba"] = 23
            data["entries"][0]["size"] = 4096
            inventory.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "exceeds raw image"):
                probe(image, inventory, sample_bytes=2048)

    def test_duplicate_or_missing_inventory_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder)
            data = json.loads(inventory.read_text())
            data["entries"].append(dict(data["entries"][0]))
            inventory.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "duplicate inventory path"):
                probe(image, inventory, sample_bytes=2048)
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder)
            with self.assertRaisesRegex(ValueError, "absent from inventory"):
                probe(image, inventory, paths=["/BIN/NOT-THERE.BIN;1"])

    def test_sample_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            image, inventory = fixture(folder)
            with self.assertRaisesRegex(ValueError, "sample-bytes"):
                probe(image, inventory, sample_bytes=0)
            with self.assertRaisesRegex(ValueError, "sample-bytes"):
                probe(image, inventory, sample_bytes=1024 * 1024 + 1)


if __name__ == "__main__":
    unittest.main()
