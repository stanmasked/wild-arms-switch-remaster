#!/usr/bin/env python3
"""Synthetic bundle integration tests; no real NRO/emulator execution."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from audit_field_capture import (
    EXPECTED_BACKGROUNDS, EXPECTED_BARS, HEIGHT, make_png, NAMES, WIDTH
)
from audit_switch_nro import read_nro
from prepare_field_emulator_bundle import HandoffError, make_handoff

SOURCE_COMMIT = "1" * 40


def fixture(directory):
    root = Path(directory)
    native = root / "build"
    native.mkdir()
    nro = bytearray(0x400)
    nro[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", nro, 0x18, len(nro))
    struct.pack_into("<II", nro, 0x20, 0, 0x200)
    struct.pack_into("<II", nro, 0x28, 0x200, 0x80)
    struct.pack_into("<II", nro, 0x30, 0x300, 0x20)
    nro_path = native / "wild_arms_field.nro"
    nro_path.write_bytes(nro)
    audit_path = native / "wild_arms_field.nro.audit.json"
    audit_path.write_text(json.dumps(read_nro(nro_path)), encoding="utf-8")
    ref = root / "reference"
    ref.mkdir()
    manifest = {
        "kind": "host_reference_not_emulator_capture",
        "width": WIDTH, "height": HEIGHT,
        "round_trip_pixels_equal": True,
        "frames": [],
    }
    for i, name in enumerate(NAMES):
        index = 0 if i == len(NAMES) - 1 else i
        rgb = bytearray(bytes([index, index, index]) * (WIDTH * HEIGHT))
        rgb[:3] = bytes(EXPECTED_BARS[i])
        pos = 100 * WIDTH * 3
        rgb[pos:pos+3] = bytes(EXPECTED_BACKGROUNDS[i])
        png = make_png(bytes(rgb))
        (ref / (name + ".png")).write_bytes(png)
        manifest["frames"].append({
            "scene": name,
            "status_rgb": list(EXPECTED_BARS[i]),
            "png_sha256": hashlib.sha256(png).hexdigest(),
            "raw_rgb_sha256": hashlib.sha256(rgb).hexdigest(),
        })
    (ref / "capture_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    return nro_path, audit_path, ref


class HandoffTests(unittest.TestCase):
    def test_bundle_has_provenance_scripts_and_five_images(self):
        with tempfile.TemporaryDirectory() as folder:
            nro, audit, ref = fixture(folder)
            out = Path(folder) / "handoff"
            summary = make_handoff(nro, audit, ref, out, SOURCE_COMMIT)
            self.assertEqual(summary["checkpoint_count"], 5)
            self.assertEqual(summary["emulator_execution"], "not_performed_or_verified")
            self.assertEqual(summary["nro"]["sha256"],
                             hashlib.sha256(nro.read_bytes()).hexdigest())
            self.assertTrue((out / "README.md").is_file())
            self.assertEqual(len(list((out / "reference").glob("*.png"))), 5)
            self.assertTrue((out / "tools" / "compare_field_emulator_png.py").exists())
            self.assertEqual(json.loads((out / "bundle_manifest.json").read_text()),
                             summary)

    def test_tampered_nro_audit_and_reference_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            nro, audit, ref = fixture(folder)
            original = json.loads(audit.read_text())
            audit.write_text(json.dumps({**original, "sha256": "0" * 64}))
            with self.assertRaises(HandoffError):
                make_handoff(nro, audit, ref, Path(folder) / "out", SOURCE_COMMIT)
            audit.write_text(json.dumps(original))
            scene = ref / (NAMES[2] + ".png")
            scene.write_bytes(scene.read_bytes()[:-3])
            with self.assertRaises(HandoffError):
                make_handoff(nro, audit, ref, Path(folder) / "out", SOURCE_COMMIT)

    def test_output_and_commit_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            nro, audit, ref = fixture(folder)
            out = Path(folder) / "out"
            with self.assertRaises(HandoffError):
                make_handoff(nro, audit, ref, out, "broken")
            with self.assertRaises(HandoffError):
                make_handoff(nro, audit, ref, ref, SOURCE_COMMIT)
            out.mkdir()
            (out / "stale-file.txt").write_text("previous version")
            with self.assertRaises(HandoffError):
                make_handoff(nro, audit, ref, out, SOURCE_COMMIT)


if __name__ == "__main__":
    unittest.main()
