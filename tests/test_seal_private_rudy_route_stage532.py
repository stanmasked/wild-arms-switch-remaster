"""Synthetic-only Stage532 Surf Village control seal tests; no original game bytes."""
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from seal_private_rudy_route_stage532 import (
    seal, verify, MANIFEST, ROLES, framebuffer_rgb_from_vram,
)

BIN_REF = "https://drive.google.com/file/d/synthetic-bin/view"
CUE_REF = "https://drive.google.com/file/d/synthetic-cue/view"


def png(rgb, width=320, height=240):
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))
    if len(rgb) != width*height*3:
        raise ValueError("RGB length mismatch")
    scanlines = b"".join(b"\0" + rgb[y*width*3:(y+1)*width*3]
                         for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b"")


def vram(seed):
    raw = bytearray(1024*512*2)
    for y in range(240):
        for x in range(320):
            value = (seed + y*320 + x)*37 % 32768
            struct.pack_into("<H", raw, (y*1024+x)*2, value)
    return bytes(raw)


def fixtures(tmp):
    base = Path(tmp)
    evidence = base/"evidence"
    source = base/"canonical-source"
    evidence.mkdir()
    source.mkdir()
    bin_path = source/"Wild Arms (USA).bin"
    cue_path = source/"Wild Arms (USA).cue"
    bin_path.write_bytes(b"\0"*(2352*2))
    cue_path.write_text('FILE "Wild Arms (USA).bin" BINARY\r\n  TRACK 01 MODE2/2352\r\n    INDEX 01 00:00:00\r\n')
    before_vram = vram(0)
    after_vram = vram(1)
    before_png = png(framebuffer_rgb_from_vram(before_vram))
    after_png = png(framebuffer_rgb_from_vram(after_vram))
    names = {
        "before_state": "before.state",
        "before_vram": "before.vram",
        "before_png": "before.png",
        "after_state": "after.state",
        "after_vram": "after.vram",
        "after_png": "after.png",
        "input_trace": "input.json",
    }
    contents = {
        "before_state": b"SYNTHETIC-BEFORE-STATE",
        "before_vram": before_vram,
        "before_png": before_png,
        "after_state": b"SYNTHETIC-AFTER-STATE",
        "after_vram": after_vram,
        "after_png": after_png,
        "input_trace": json.dumps({
            "schema": "wild-arms-surf-control-input-v1",
            "origin": "operator_declared_not_attested",
            "events": [
                {"frame": 0, "buttons": []},
                {"frame": 20, "buttons": ["dpad_right"]},
                {"frame": 50, "buttons": []},
            ],
        }).encode(),
    }
    for role, content in contents.items():
        (evidence/names[role]).write_bytes(content)
    return evidence, names, bin_path, cue_path


def seal_fixture(evidence, names, bin_path, cue_path):
    return seal(evidence, names, disc_bin=bin_path, disc_cue=cue_path,
                bin_ref=BIN_REF, cue_ref=CUE_REF)


class Stage532Tests(unittest.TestCase):
    def test_roundtrip_and_independent_evidence_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            result = seal_fixture(root, names, bin_path, cue_path)
            self.assertEqual(result["status"], "INTEGRITY_ONLY_NO_GAMEPLAY_ATTESTATION")
            self.assertTrue(verify(root, disc_bin=bin_path, disc_cue=cue_path))
            self.assertEqual(set(result["files"]), set(ROLES))
            self.assertNotIn("Wild Arms (USA).bin", [x["name"] for x in result["files"].values()])
            self.assertTrue(result["source_disc"]["canonical_source_not_bundled"])
            self.assertEqual(stat.S_IMODE((root/MANIFEST).stat().st_mode), 0o600)
            clone = Path(td)/"downloaded-copy"
            clone.mkdir()
            for item in root.iterdir():
                shutil.copyfile(item, clone/item.name)
            self.assertTrue(verify(clone, disc_bin=bin_path, disc_cue=cue_path))

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            seal_fixture(root, names, bin_path, cue_path)
            with self.assertRaises(FileExistsError):
                seal_fixture(root, names, bin_path, cue_path)

    def test_tampered_state_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            seal_fixture(root, names, bin_path, cue_path)
            with (root/names["after_state"]).open("ab") as f:
                f.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "differ"):
                verify(root, disc_bin=bin_path, disc_cue=cue_path)

    def test_tampered_canonical_source_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            seal_fixture(root, names, bin_path, cue_path)
            raw = bytearray(bin_path.read_bytes())
            raw[100] ^= 1
            bin_path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "canonical source"):
                verify(root, disc_bin=bin_path, disc_cue=cue_path)

    def test_tampered_manifest_attestation_claim_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            seal_fixture(root, names, bin_path, cue_path)
            p = root/MANIFEST
            record = json.loads(p.read_text())
            record["status"] = "GAMEPLAY_CONFIRMED"
            p.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "provenance"):
                verify(root, disc_bin=bin_path, disc_cue=cue_path)

    def test_identical_raw_vram_and_framebuffer_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            (root/names["after_vram"]).write_bytes((root/names["before_vram"]).read_bytes())
            (root/names["after_png"]).write_bytes((root/names["before_png"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "must differ"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_framebuffer_png_must_match_raw_vram(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            (root/names["after_png"]).write_bytes((root/names["before_png"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "does not match raw VRAM"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_wrong_framebuffer_dimensions_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            (root/names["before_png"]).write_bytes(png(bytes((1, 2, 3, 4, 5, 6)), 2, 1))
            with self.assertRaisesRegex(ValueError, "320x240"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_cue_must_match_bin_and_track(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            cue_path.write_text('FILE "unrelated.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00\n')
            with self.assertRaisesRegex(ValueError, "must match"):
                seal_fixture(root, names, bin_path, cue_path)
            cue_path.write_text('FILE "Wild Arms (USA).bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n')
            with self.assertRaisesRegex(ValueError, "MODE2/2352"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_bad_journal_event_and_duplicate_key(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            event = root/names["input_trace"]
            record = json.loads(event.read_text())
            record["events"][2]["frame"] = 20
            event.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "ordered"):
                seal_fixture(root, names, bin_path, cue_path)
            event.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_reject_non_neutral_trace_ends(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            event = root/names["input_trace"]
            record = json.loads(event.read_text())
            record["events"][-1]["buttons"] = ["dpad_right"]
            event.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "end at neutral"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_symlink_and_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            target = root/names["before_state"]
            saved = root/"saved.state"
            target.rename(saved)
            target.symlink_to(saved)
            with self.assertRaisesRegex(ValueError, "single-link"):
                seal_fixture(root, names, bin_path, cue_path)
            target.unlink()
            os.link(saved, target)
            with self.assertRaisesRegex(ValueError, "single-link"):
                seal_fixture(root, names, bin_path, cue_path)

    def test_path_traversal_and_role_alias_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            with self.assertRaises(ValueError):
                seal_fixture(root, {**names, "before_state": "../escape"}, bin_path, cue_path)
            with self.assertRaises(ValueError):
                seal_fixture(root, {**names, "after_state": names["before_state"]}, bin_path, cue_path)

    def test_manifest_missing_role_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            seal_fixture(root, names, bin_path, cue_path)
            p = root/MANIFEST
            record = json.loads(p.read_text())
            record["files"].pop("after_png")
            p.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "roles"):
                verify(root, disc_bin=bin_path, disc_cue=cue_path)

    def test_corrupted_framebuffer_png_rejected_before_seal(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            (root/names["after_png"]).write_bytes(b"not-a-png")
            with self.assertRaises(ValueError):
                seal_fixture(root, names, bin_path, cue_path)
            self.assertFalse((root/MANIFEST).exists())

    def test_no_manifest_on_failed_seal(self):
        with tempfile.TemporaryDirectory() as td:
            root, names, bin_path, cue_path = fixtures(td)
            (root/names["before_vram"]).write_bytes(b"unaligned")
            with self.assertRaisesRegex(ValueError, "exactly 1 MiB"):
                seal_fixture(root, names, bin_path, cue_path)
            self.assertFalse((root/MANIFEST).exists())


if __name__ == "__main__":
    unittest.main()
