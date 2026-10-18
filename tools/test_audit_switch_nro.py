#!/usr/bin/env python3
"""Synthetic fixture tests for homebrew NRO0 and ASET structural validation."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from audit_switch_nro import NroFormatError, read_nro


def make_nro(with_assets=False):
    payload = bytearray(0x400)
    payload[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", payload, 0x18, len(payload))
    struct.pack_into("<II", payload, 0x20, 0x80, 0x100)
    struct.pack_into("<II", payload, 0x28, 0x200, 0x80)
    struct.pack_into("<II", payload, 0x30, 0x300, 0x20)
    struct.pack_into("<I", payload, 0x38, 0x10)
    struct.pack_into("<I", payload, 0x04, 0x90)
    payload[0x80:0x180] = b"\x23" * 0x100
    payload[0x200:0x280] = b"\x44" * 0x80
    payload[0x300:0x320] = b"\x55" * 0x20
    if with_assets:
        aset = bytearray(0x38 + 0x20 + 0x40)
        aset[:4] = b"ASET"
        struct.pack_into("<QQ", aset, 8, 0x38, 0x20)
        struct.pack_into("<QQ", aset, 24, 0x58, 0x40)
        aset[0x38:0x58] = b"\xff\xd8" + b"\x00" * 30
        aset[0x58:0x98] = b"\x77" * 0x40
        payload += aset
    return payload


class NroAuditTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field.nro"
            path.write_bytes(data)
            return read_nro(path)

    def rejected(self, payload):
        with self.assertRaises(NroFormatError):
            self.parse(payload)

    def test_minimal_nro(self):
        payload = make_nro()
        report = self.parse(payload)
        self.assertEqual(report["format"], "NRO0")
        self.assertEqual(report["image_size"], 0x400)
        self.assertEqual(report["bss_size"], 0x10)
        self.assertIsNone(report["assets"])
        self.assertEqual(report["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual([s["name"] for s in report["segments"]],
                         ["text", "rodata", "data"])
        self.assertEqual(report["validation"],
                         "static_container_only_not_executed")

    def test_assets_and_sections(self):
        payload = make_nro(with_assets=True)
        report = self.parse(payload)
        self.assertEqual(report["assets"]["header_offset"], 0x400)
        self.assertEqual([x["size"] for x in report["assets"]["sections"]],
                         [0x20, 0x40, 0])

    def test_reject_bad_signature_and_header_bounds(self):
        base = make_nro()
        copy = bytearray(base)
        copy[0x10] = 0
        self.rejected(copy)
        copy = bytearray(base)
        struct.pack_into("<I", copy, 0x18, 0x7F)
        self.rejected(copy)
        copy = bytearray(base)
        struct.pack_into("<I", copy, 0x18, 0x401)
        self.rejected(copy)
        self.rejected(b"\x00" * 16)

    def test_reject_segment_overlap_or_outside(self):
        copy = make_nro()
        struct.pack_into("<II", copy, 0x28, 0x100, 0x100)
        self.rejected(copy)
        copy = make_nro()
        struct.pack_into("<II", copy, 0x30, 0x3F0, 0x100)
        self.rejected(copy)
        copy = make_nro()
        struct.pack_into("<II", copy, 0x20, 0x80, 0)
        self.rejected(copy)
        copy = make_nro()
        struct.pack_into("<I", copy, 0x28, 0x203)
        self.rejected(copy)

    def test_reject_invalid_mod_version_and_flags(self):
        for offset, value in ((0x04, 0x700), (0x14, 1), (0x1C, 2)):
            copy = make_nro()
            struct.pack_into("<I", copy, offset, value)
            self.rejected(copy)

    def test_reject_trailing_garbage_or_asset_overlap(self):
        self.rejected(make_nro() + b"garbage")
        copy = make_nro(with_assets=True)
        struct.pack_into("<QQ", copy, 0x400 + 24, 0x40, 0x40)
        self.rejected(copy)
        copy = make_nro(with_assets=True)
        struct.pack_into("<QQ", copy, 0x400 + 8, 0x38, 0xFFF)
        self.rejected(copy)
        copy = make_nro(with_assets=True)
        copy[0x400] ^= 1
        self.rejected(copy)


if __name__ == "__main__":
    unittest.main()
