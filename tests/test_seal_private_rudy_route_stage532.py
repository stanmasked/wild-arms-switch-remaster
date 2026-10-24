"""Synthetic-only Stage532 gameplay route seal tests; no original game bytes."""
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
from seal_private_rudy_route_stage532 import seal, verify, MANIFEST, ROLES


def png(rgb):
    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0" + rgb)) + chunk(b"IEND", b"")


def fixtures(root):
    root = Path(root)
    names = {role: role.replace("_", "-") + ".dat" for role in ROLES}
    names["disc_bin"] = "example.bin"
    names["disc_cue"] = "example.cue"
    names["selection_png"] = "selection.png"
    names["arrival_png"] = "arrival.png"
    contents = {"disc_bin": b"\0" * 2352 * 2,
                "disc_cue": b'FILE "example.bin" BINARY\r\n  TRACK 01 MODE2/2352\r\n    INDEX 01 00:00:00\r\n',
                "selection_state": b"SYNTHETIC-SELECT-STATE",
                "arrival_state": b"SYNTHETIC-ARRIVAL-STATE",
                "selection_png": png(bytes((4, 5, 6, 7, 8, 9))),
                "arrival_png": png(bytes((10, 11, 12, 13, 14, 15))),
                "input_trace": json.dumps({"schema": "wild-arms-rudy-route-input-v1",
                    "origin": "operator_declared_not_attested", "events": [
                        {"frame": 0, "buttons": []},
                        {"frame": 6, "buttons": ["cross"]},
                        {"frame": 7, "buttons": []}]}).encode()}
    for role, content in contents.items():
        (root / names[role]).write_bytes(content)
    return names


class Stage532Tests(unittest.TestCase):
    def test_roundtrip_and_independent_copy(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "source"
            q = Path(td) / "download"
            p.mkdir(); q.mkdir()
            names = fixtures(p)
            sealed = seal(p, names)
            self.assertEqual(sealed["status"], "INTEGRITY_ONLY_NO_GAMEPLAY_ATTESTATION")
            self.assertTrue(verify(p))
            for f in p.iterdir():
                shutil.copyfile(f, q / f.name)
            self.assertTrue(verify(q))
            self.assertEqual(stat.S_IMODE((p / MANIFEST).stat().st_mode), 0o600)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            seal(td, names)
            with self.assertRaises(FileExistsError):
                seal(td, names)

    def test_tampered_state_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            seal(td, names)
            with (Path(td) / names["arrival_state"]).open("ab") as f:
                f.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "differ"):
                verify(td)

    def test_tampered_manifest_declared_attestation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            seal(td, names)
            p = Path(td) / MANIFEST
            data = json.loads(p.read_text())
            data["status"] = "GAMEPLAY_CONFIRMED"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "provenance"):
                verify(td)

    def test_identical_png_raster_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            (Path(td) / names["arrival_png"]).write_bytes((Path(td) / names["selection_png"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "must differ"):
                seal(td, names)

    def test_identical_states_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            (Path(td) / names["arrival_state"]).write_bytes((Path(td) / names["selection_state"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "must not be identical"):
                seal(td, names)

    def test_cue_must_match_bin_and_track(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            cue = Path(td) / names["disc_cue"]
            cue.write_text('FILE "unrelated.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00\n')
            with self.assertRaisesRegex(ValueError, "must match"):
                seal(td, names)
            cue.write_text('FILE "example.bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n')
            with self.assertRaisesRegex(ValueError, "MODE2/2352"):
                seal(td, names)

    def test_bad_journal_event_and_duplicate_key(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            event = Path(td) / names["input_trace"]
            record = json.loads(event.read_text())
            record["events"][2]["frame"] = 6
            event.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "ordered"):
                seal(td, names)
            event.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                seal(td, names)

    def test_reject_non_neutral_trace_ends(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            event = Path(td) / names["input_trace"]
            record = json.loads(event.read_text())
            record["events"][-1]["buttons"] = ["cross"]
            event.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "neutral"):
                seal(td, names)

    def test_symlink_or_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            target = Path(td) / names["selection_state"]
            moved = Path(td) / "saved"
            target.rename(moved)
            target.symlink_to(moved)
            with self.assertRaisesRegex(ValueError, "single-link"):
                seal(td, names)
            target.unlink()
            os.link(moved, target)
            with self.assertRaisesRegex(ValueError, "single-link"):
                seal(td, names)

    def test_path_traversal_and_role_alias_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            with self.assertRaises(ValueError):
                seal(td, {**names, "selection_state": "../escape"})
            with self.assertRaises(ValueError):
                seal(td, {**names, "arrival_state": names["selection_state"]})

    def test_manifest_missing_role_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            seal(td, names)
            p = Path(td) / MANIFEST
            data = json.loads(p.read_text())
            data["files"].pop("arrival_png")
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "roles"):
                verify(td)

    def test_corrupted_screenshot_rejected_before_seal(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            (Path(td) / names["arrival_png"]).write_bytes(b"not-a-png")
            with self.assertRaises(ValueError):
                seal(td, names)

    def test_no_manifest_on_failed_seal(self):
        with tempfile.TemporaryDirectory() as td:
            names = fixtures(td)
            (Path(td) / names["disc_bin"]).write_bytes(b"unaligned")
            with self.assertRaisesRegex(ValueError, "aligned"):
                seal(td, names)
            self.assertFalse((Path(td) / MANIFEST).exists())


if __name__ == "__main__":
    unittest.main()
