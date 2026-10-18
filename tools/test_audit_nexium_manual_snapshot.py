#!/usr/bin/env python3
"""Synthetic desktop fixtures for Stage 292 strict manual snapshot audit."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from audit_field_capture import NAMES, WIDTH, HEIGHT
from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H
from audit_nexium_manual_snapshot import PHASES, audit_manual_snapshot
from test_audit_nexium_checkpoints import refs, desktop


def fixture(root):
    root = Path(root)
    ref = root / "ref"
    obs = root / "obs"
    refs(ref)
    obs.mkdir()
    for name, idx in PHASES:
        if idx is not None:
            img = desktop(ref / (NAMES[idx] + ".png"))
        else:
            with Image.open(ref / (NAMES[1] + ".png")) as image:
                frame = image.convert("RGB")
            d = ImageDraw.Draw(frame)
            d.rectangle((0,0,WIDTH - 1,9), fill=(63,191,138))
            d.rectangle((576-19,232-19,576+18,232+18),fill=(201,67,76))
            d.rectangle((576+10,232-5,576+19,232+4),fill=(22,27,42))
            img = Image.new("RGB",SCREEN_SIZE,(15,15,17))
            img.paste(frame.resize((VIEW_W,VIEW_H),Image.Resampling.NEAREST),
                      (VIEW_X,0))
        # NeXium performance HUD is not game output.
        ImageDraw.Draw(img).rectangle((VIEW_X,0,VIEW_X+219,153),
                                       fill=(44,55,66))
        img.save(obs / (name + ".png"))
    return ref, obs


class NeXiumManualSnapshotAuditTests(unittest.TestCase):
    def test_valid_two_round_trips(self):
        with tempfile.TemporaryDirectory() as td:
            ref, obs = fixture(td)
            result = audit_manual_snapshot(ref,obs,Path(td)/"audit.json")
            self.assertTrue(result["manual_quicksave_and_event_restore_confirmed"])
            self.assertEqual(len(result["phases"]),8)
            self.assertEqual(result["phases"][2]["mismatched_visible_pixels"],0)

    def test_moving_player_does_not_count_as_restored(self):
        with tempfile.TemporaryDirectory() as td:
            ref, obs = fixture(td)
            target = obs / "03_start_restored.png"
            with Image.open(target) as png:
                image = png.convert("RGB")
            image.putpixel((700,350),(0,0,0))
            image.save(target)
            result = audit_manual_snapshot(ref,obs,Path(td)/"audit.json")
            self.assertFalse(result["manual_quicksave_and_event_restore_confirmed"])
            self.assertEqual(result["phases"][3]["mismatched_visible_pixels"],1)

    def test_acknowledgment_must_be_unpaused_before_restoring_event(self):
        with tempfile.TemporaryDirectory() as td:
            ref, obs = fixture(td)
            target = obs / "06_event_acknowledged.png"
            desktop(ref / (NAMES[1] + ".png")).save(target)
            result = audit_manual_snapshot(ref,obs,Path(td)/"audit.json")
            self.assertFalse(result["manual_quicksave_and_event_restore_confirmed"])
            self.assertFalse(result["phases"][6]["matched"])

    def test_missing_frame_and_reference_mutation_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ref, obs = fixture(td)
            (obs / "07_event_restored.png").unlink()
            with self.assertRaises(ValueError):
                audit_manual_snapshot(ref,obs,Path(td)/"audit.json")
        with tempfile.TemporaryDirectory() as td:
            ref, obs = fixture(td)
            (ref / (NAMES[0] + ".png")).write_bytes(b"tampered")
            with self.assertRaises((ValueError, OSError)):
                audit_manual_snapshot(ref,obs,Path(td)/"audit.json")


if __name__ == "__main__":
    unittest.main()
