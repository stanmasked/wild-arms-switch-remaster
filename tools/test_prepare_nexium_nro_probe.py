#!/usr/bin/env python3
"""No emulator required: check diagnostic padding never modifies the NRO."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from audit_switch_nro import read_nro
from prepare_nexium_nro_probe import build_loader_probe


def sample_nro():
    data = bytearray(0x400)
    data[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", data, 0x18, len(data))
    struct.pack_into("<II", data, 0x20, 0, 0x200)
    struct.pack_into("<II", data, 0x28, 0x200, 0x100)
    struct.pack_into("<II", data, 0x30, 0x300, 0x100)
    return bytes(data)


class LoaderProbeTests(unittest.TestCase):
    def test_exact_sixteen_byte_probe_preserves_real_nro(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "real.nro"
            output = root / "compat.nro"
            report = root / "diagnostic.json"
            source.write_bytes(sample_nro())
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            result = build_loader_probe(source, output, report)
            self.assertEqual(source.read_bytes(), sample_nro())
            self.assertEqual(before, result["original_nro_sha256"])
            self.assertTrue(output.read_bytes().startswith(source.read_bytes()))
            self.assertEqual(len(output.read_bytes()), len(source.read_bytes()) + 16)
            self.assertFalse(result["probe_is_valid_standard_nro"])
            self.assertFalse(result["guest_execution_verified"])
            self.assertTrue(report.exists())

    def test_reject_existing_destination_and_same_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "real.nro"
            source.write_bytes(sample_nro())
            with self.assertRaises(ValueError):
                build_loader_probe(source, source, root / "bad.json")
            dest = root / "compat.nro"
            dest.write_bytes(b"existing")
            with self.assertRaises(ValueError):
                build_loader_probe(source, dest, root / "bad.json")

    def test_reject_when_data_does_not_finish_at_real_eof(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "real.nro"
            invalid_for_probe = bytearray(sample_nro())
            struct.pack_into("<I", invalid_for_probe, 0x34, 0x80)
            source.write_bytes(invalid_for_probe)
            self.assertEqual(read_nro(source)["format"], "NRO0")
            with self.assertRaises(ValueError):
                build_loader_probe(source, root / "padded.nro", root / "bad.json")


if __name__ == "__main__":
    unittest.main()
