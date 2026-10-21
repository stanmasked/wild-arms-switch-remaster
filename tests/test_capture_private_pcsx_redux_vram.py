"""Synthetic-only tests: no original game data, no network or emulator needed."""
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from capture_private_pcsx_redux_vram import (  # noqa: E402
    DEFAULT_URL, RAW_VRAM_BYTES, _publish_without_overwrite,
    capture_private_vram, download_private_vram, validate_endpoint,
    verify_private_vram,
)


class FakeResponse:
    def __init__(self, payload, *, url=DEFAULT_URL, status=200):
        self.data = BytesIO(payload)
        self.url = url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.data.close()

    def geturl(self):
        return self.url

    def read(self, count):
        return self.data.read(count)


class FakeOpener:
    def __init__(self, payload, *, url=DEFAULT_URL, status=200):
        self.payload, self.url, self.status = payload, url, status
        self.calls = 0

    def open(self, req, timeout):
        self.calls += 1
        assert req.get_method() == "GET"
        assert timeout == 10
        return FakeResponse(self.payload, url=self.url, status=self.status)


def synthetic_raw():
    return bytes(range(256)) * (RAW_VRAM_BYTES // 256)


class Stage429CaptureTests(unittest.TestCase):
    def test_exact_local_endpoint_only(self):
        self.assertEqual(validate_endpoint(DEFAULT_URL), DEFAULT_URL)
        self.assertEqual(validate_endpoint("http://[::1]:8080/api/v1/gpu/vram/raw"),
                         "http://[::1]:8080/api/v1/gpu/vram/raw")
        for url in ("https://127.0.0.1:8080/api/v1/gpu/vram/raw",
                    "http://example.org:8080/api/v1/gpu/vram/raw",
                    "http://localhost:8080/api/v1/gpu/vram/raw",
                    "http://127.0.0.2:8080/api/v1/gpu/vram/raw",
                    "http://127.0.0.1:8080/api/v1/gpu/vram/raw?x=1",
                    "http://127.0.0.1:8080/api/v1/cpu/ram/raw",
                    "http://someone@127.0.0.1:8080/api/v1/gpu/vram/raw"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_endpoint(url)

    def test_exact_size_and_get(self):
        data = synthetic_raw()
        opener = FakeOpener(data)
        self.assertEqual(download_private_vram(opener=opener), data)
        self.assertEqual(opener.calls, 1)

    def test_short_and_oversized_capture_rejected(self):
        for size in (0, 1, RAW_VRAM_BYTES - 1, RAW_VRAM_BYTES + 1):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "exactly"):
                download_private_vram(opener=FakeOpener(bytes(size)))

    def test_redirect_and_error_rejected(self):
        with self.assertRaisesRegex(ValueError, "redirected"):
            download_private_vram(opener=FakeOpener(synthetic_raw(),
                url="http://external.invalid/api/v1/gpu/vram/raw"))
        with self.assertRaisesRegex(ValueError, "200"):
            download_private_vram(opener=FakeOpener(synthetic_raw(), status=503))

    def test_invalid_timeout_denied(self):
        for timeout in (0, 121, True, -1, "ten"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                download_private_vram(opener=FakeOpener(synthetic_raw()),
                                      timeout=timeout)

    def test_private_capture_manifest_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)
            manifest = capture_private_vram(output, basename="test001",
                                            opener=FakeOpener(synthetic_raw()))
            self.assertEqual(manifest["bytes"], RAW_VRAM_BYTES)
            self.assertEqual(len(manifest["vram_sha256"]), 64)
            self.assertTrue(manifest["game_map_and_frame_number_unverified"])
            self.assertTrue(manifest["little_endian_word_order_assumed_not_independently_verified"])
            self.assertTrue(manifest["no_gp0_packet_trace_included"])
            self.assertEqual((output/"test001.u16le.bin").stat().st_size,
                             RAW_VRAM_BYTES)
            self.assertTrue(verify_private_vram(output, basename="test001")["verified"])
            self.assertNotIn("original_pixels", json.dumps(manifest))
            if os.name != "nt":
                self.assertEqual((output/"test001.u16le.bin").stat().st_mode & 0o777, 0o600)
                self.assertEqual((output/"test001.capture.json").stat().st_mode & 0o777, 0o600)

    def test_no_clobber_existing_snapshot_without_opening_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            existing = folder/"surf_village_vram.u16le.bin"
            existing.write_bytes(b"KEEP")
            opener = FakeOpener(synthetic_raw())
            with self.assertRaises(FileExistsError):
                capture_private_vram(folder, opener=opener)
            self.assertEqual(existing.read_bytes(), b"KEEP")
            self.assertEqual(opener.calls, 0)

    def test_existing_manifest_also_blocks_capture(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            metadata=folder/"surf_village_vram.capture.json"
            metadata.write_bytes(b"KEEP")
            with self.assertRaises(FileExistsError):
                capture_private_vram(folder, opener=FakeOpener(synthetic_raw()))
            self.assertEqual(metadata.read_bytes(), b"KEEP")
            self.assertFalse((folder/"surf_village_vram.u16le.bin").exists())

    def test_reject_unsafe_filename_and_uncreated_directory(self):
        with tempfile.TemporaryDirectory() as td:
            for basename in ("../steal", "/tmp/test", "name.ext", "", " x", "a"*65):
                with self.subTest(basename=basename), self.assertRaises(ValueError):
                    capture_private_vram(td, basename=basename,
                        opener=FakeOpener(synthetic_raw()))
            with self.assertRaisesRegex(ValueError, "must already exist"):
                capture_private_vram(Path(td)/"not-created",
                    opener=FakeOpener(synthetic_raw()))

    def test_metadata_detects_bit_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            capture_private_vram(folder, opener=FakeOpener(synthetic_raw()))
            path=folder/"surf_village_vram.u16le.bin"
            with path.open("r+b") as fp:
                fp.seek(44)
                fp.write(b"Z")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_private_vram(folder)

    def test_metadata_detects_truncation(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            capture_private_vram(folder, opener=FakeOpener(synthetic_raw()))
            path=folder/"surf_village_vram.u16le.bin"
            with path.open("r+b") as fp:
                fp.truncate(16)
            with self.assertRaisesRegex(ValueError, "size changed"):
                verify_private_vram(folder)

    def test_metadata_refuses_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            capture_private_vram(folder, opener=FakeOpener(synthetic_raw()))
            path=folder/"surf_village_vram.capture.json"
            meta=json.loads(path.read_text())
            meta["vram_filename"]="../elsewhere.bin"
            path.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError, "malformed"):
                verify_private_vram(folder)

    def test_failed_metadata_publish_rolls_back_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            from capture_private_pcsx_redux_vram import os as target_os
            true_link=target_os.link
            counter=[0]
            def fail_second(*args,**kwargs):
                counter[0] += 1
                if counter[0] == 2:
                    raise OSError("synthetic second link error")
                return true_link(*args,**kwargs)
            with patch("capture_private_pcsx_redux_vram.os.link",side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "synthetic"):
                    capture_private_vram(folder, opener=FakeOpener(synthetic_raw()))
            self.assertEqual(list(folder.iterdir()), [])

    def test_failed_download_creates_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            with self.assertRaises(ValueError):
                capture_private_vram(folder, opener=FakeOpener(b"too short"))
            self.assertEqual(list(folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
