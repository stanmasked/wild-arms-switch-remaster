#!/usr/bin/env python3
"""Adversarial tests for the two-process NeXium SD battle journal oracle."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image, ImageDraw
from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, screen_point
from audit_nexium_battle_persistence import NAMES, audit_persistence

MAP = (63, 191, 138)
GOLD = (245, 183, 66)
WHITE = (246, 247, 252)
PANEL = (31, 45, 66)
FIELD = (14, 20, 34)


def save_fake_journal(path, generation, exits):
    body = bytearray(36)
    body[:4] = b"WABR"
    body[4] = 1
    body[5] = 3
    struct.pack_into("<I", body, 16, exits)
    struct.pack_into("<I", body, 32, zlib.crc32(body[:32]))
    payload = bytearray(52)
    payload[:4] = b"WABJ"
    struct.pack_into("<Q", payload, 4, generation)
    payload[12:48] = body
    struct.pack_into("<I", payload, 48, zlib.crc32(payload[:48]))
    Path(path).write_bytes(payload)


def image(name):
    native = Image.new("RGB", (1280, 720), FIELD)
    d = ImageDraw.Draw(native)
    d.rectangle((0, 0, 1279, 9), fill=MAP)
    d.rectangle((340, 230, 369, 250), fill=(201, 67, 76))
    if name in ("01_first_zl_zero", "03_reboot_zl_one"):
        d.rectangle((690, 612, 1239, 707), fill=PANEL)
        d.rectangle((690, 612, 1239, 615), fill=GOLD)
        if name == "01_first_zl_zero":
            d.rectangle((787, 679, 790, 684), fill=WHITE)
        else:
            d.rectangle((791, 679, 796, 684), fill=WHITE)
            d.rectangle((921, 677, 925, 682), fill=WHITE)
    desktop = Image.new("RGB", SCREEN_SIZE)
    desktop.paste(
        native.resize((VIEW_W, VIEW_H), Image.Resampling.NEAREST),
        (VIEW_X, 0))
    return desktop


def setup(folder):
    folder = Path(folder)
    shots = folder / "screens"
    shots.mkdir()
    for name in NAMES:
        image(name).save(shots / (name + ".png"))
    j1, a, b = (folder / n for n in ("copy.a", "battle-progress.a",
                                   "battle-progress.b"))
    save_fake_journal(j1, 1, 1)
    save_fake_journal(a, 1, 1)
    save_fake_journal(b, 2, 2)
    return shots, j1, a, b, folder / "result.json"


def evaluate(paths):
    return audit_persistence(*paths)


class RealGuestPersistenceAuditorTests(unittest.TestCase):
    def test_positive_observed_image_and_two_generation_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            r = evaluate(setup(root))
            self.assertTrue(r["all_checks_passed"], r["checks"])
            self.assertEqual(len(r["checks"]), 8)
            self.assertEqual(len(r["sha256"]), 6)

    def test_missing_frame_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            (paths[0] / "03_reboot_zl_one.png").unlink()
            with self.assertRaises(ValueError):
                evaluate(paths)

    def test_extra_frame_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            image("00_first_field").save(paths[0] / "unexpected.png")
            with self.assertRaises(ValueError):
                evaluate(paths)

    def test_corrupt_old_outer_crc_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            a = bytearray(paths[1].read_bytes())
            a[48] ^= 0x80
            paths[1].write_bytes(a)
            with self.assertRaises(ValueError):
                evaluate(paths)

    def test_corrupt_inner_record_checksum_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            b = bytearray(paths[3].read_bytes())
            b[44] ^= 1
            struct.pack_into("<I", b, 48, zlib.crc32(b[:48]))
            paths[3].write_bytes(b)
            with self.assertRaises(ValueError):
                evaluate(paths)

    def test_wrong_recovered_generation_or_counter_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            save_fake_journal(paths[3], 2, 1)
            r = evaluate(paths)
            self.assertFalse(r["checks"]["second_guest_commits_next_generation_with_unmodified_prior"])

    def test_first_guest_did_not_commit_cannot_pass(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            save_fake_journal(paths[1], 1, 0)
            r = evaluate(paths)
            self.assertFalse(r["checks"]["first_guest_wrote_only_valid_generation_one"])

    def test_missing_rebooted_one_glyph_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            image("00_first_field").save(paths[0] / "03_reboot_zl_one.png")
            r = evaluate(paths)
            self.assertFalse(r["checks"]["second_fresh_guest_reloads_one_retreat_into_ZL"])

    def test_changed_returned_field_is_detected(self):
        with tempfile.TemporaryDirectory() as root:
            paths = setup(root)
            name = paths[0] / "05_reboot_after_second_retreat.png"
            with Image.open(name) as im:
                canvas = im.convert("RGB")
            x, y = screen_point(600, 400)
            canvas.putpixel((x, y), (0, 250, 11))
            canvas.save(name)
            r = evaluate(paths)
            self.assertFalse(r["checks"]["second_guest_B_return_keeps_identical_map"])


if __name__ == "__main__":
    unittest.main()
