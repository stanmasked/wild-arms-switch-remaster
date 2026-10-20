#!/usr/bin/env python3
"""Host-synthetic adversarial fixtures; actual NeXium guest proof is separate."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import screen_point
from audit_nexium_battle_alternating_faults import GLYPH, GREEN, PANEL
from audit_nexium_battle_external_backup_restore import audit_external_recovery
from stage_verified_battle_backup import prepare_recovery
from test_audit_nexium_battle_alternating_faults import four_panel
from test_audit_nexium_battle_double_corruption import make_fixture
from test_audit_nexium_battle_two_victories import picture, journal


def exits(image, count):
    for row, mask in enumerate(GLYPH[count]):
        for col in range(5):
            ink = (246,247,252) if (mask >> (4-col)) & 1 else PANEL
            for dy in (0,1):
                image.putpixel(screen_point(789+2*col+1, 677+2*row+dy), ink)


def fixture(root):
    root = Path(root)
    prior = make_fixture(root)
    backup_a, backup_b = prior[2], prior[3]
    corrupt_a, corrupt_b = prior[8], prior[9]
    # Separate archived fault evidence from the new simulated live SDMC.
    # Restore staging must never be placed under the live save directory.
    live_dir = root / "isolated-live-sdmc"
    live_dir.mkdir()
    live_a, live_b = live_dir / "battle-progress.a", live_dir / "battle-progress.b"
    shutil.copyfile(corrupt_a, live_a)
    shutil.copyfile(corrupt_b, live_b)
    sha_a = hashlib.sha256(backup_a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(backup_b.read_bytes()).hexdigest()
    out = root/"staged"
    prepare_recovery(live_a, live_b, backup_a, backup_b,
                     sha_a, sha_b, out, execute=True)
    restored = out/"battle-progress.a"
    screens = root/"screens371"
    screens.mkdir()
    initial= four_panel()
    exits(initial,2)
    saved= four_panel()
    exits(saved,3)
    frames={
        "00_twentyfifth_restore_four_wins":initial,
        "01_twentyfifth_after_retreat":picture("07_third_retreat"),
        "02_twentyfifth_saved_after_retreat":saved,
        "03_twentysixth_reload_saved_four_wins":saved,
    }
    for name,img in frames.items():
        img.save(screens/(name+".png"))
    after25_a=root/"after25.a"
    after25_b=root/"after25.b"
    after26_a=root/"after26.a"
    after26_b=root/"after26.b"
    shutil.copyfile(restored, after25_a)
    journal(after25_b,7,3,4,3,32,48)
    shutil.copyfile(after25_a,after26_a)
    shutil.copyfile(after25_b,after26_b)
    pids=root/"new-pids"
    pids.write_text("twentyfifth 1012\ntwentysixth 1013\n", encoding="ascii")
    keys=root/"keys"
    events=(("twentyfifth","x"),("twentyfifth","e"),
            ("twentyfifth","x"),("twentysixth","x"))
    keys.write_text("".join(f"{n} 2026-10-20T20:00:00Z {key}\n"
                            for n,key in events),encoding="ascii")
    return (screens,prior[1],restored,corrupt_a,corrupt_b,
            live_a,live_b,after25_a,after25_b,after26_a,
            after26_b,out/"recovery-manifest.json",prior[11],pids,
            keys,root/"audit.json")


class IsolatedGuestRestoreTests(unittest.TestCase):
    def test_valid_restored_gen6_then_saved_gen7_without_duplicate_rewards(self):
        with tempfile.TemporaryDirectory() as d:
            r=audit_external_recovery(*fixture(d))
            self.assertTrue(r["all_checks_passed"],r["checks"])
            self.assertEqual(len(r["checks"]),11)

    def test_missing_required_guest_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            (a[0]/"03_twentysixth_reload_saved_four_wins.png").unlink()
            with self.assertRaises(ValueError):
                audit_external_recovery(*a)

    def test_unexpected_guest_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            picture("01_first_victory").save(a[0]/"fake.png")
            with self.assertRaises(ValueError):
                audit_external_recovery(*a)

    def test_restored_generation_from_wrong_backup_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            journal(a[2],5,1,4,1,32,48)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "trusted_gen6_backup_restored_only_into_separate_new_root"])

    def test_new_B_must_not_double_rewards(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            journal(a[8],7,3,4,3,40,60)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "independent_twentyfifth_save_writes_generation_seven_B"])

    def test_restart_must_not_modify_prior_B(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            journal(a[10],7,3,4,3,32,49)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "twentysixth_read_only_reboot_never_rewrites_new_B"])

    def test_both_damaged_originals_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            raw=bytearray(a[5].read_bytes())
            raw[48]^=0x01
            a[5].write_bytes(raw)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "two_corrupt_originals_preserved_without_mutation"])

    def test_manifest_claiming_auto_install_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            data=json.loads(a[11].read_text())
            data["installed_to_live_sdmc"]=True
            a[11].write_text(json.dumps(data))
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "trusted_gen6_backup_restored_only_into_separate_new_root"])

    def test_false_corrupt_warning_in_restored_guest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            path=a[0]/"00_twentyfifth_restore_four_wins.png"
            with Image.open(path) as im:
                img=im.convert("RGB")
            img.putpixel(screen_point(690,554),(201,67,76))
            img.putpixel(screen_point(695,559),(31,45,66))
            img.putpixel(screen_point(711,565),(246,247,252))
            img.putpixel(screen_point(711,585),(201,67,76))
            img.putpixel(screen_point(1239,606),(201,67,76))
            img.save(path)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "twentyfifth_fresh_boot_reads_four_wins_32EXP_48Gella"])

    def test_wrong_initial_retreat_count_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            path=a[0]/"00_twentyfifth_restore_four_wins.png"
            with Image.open(path) as im:
                img=im.convert("RGB")
            exits(img,3)
            img.save(path)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "twentyfifth_fresh_boot_reads_four_wins_32EXP_48Gella"])

    def test_duplicate_or_missing_process_pids_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            a[13].write_text("twentyfifth 1011\ntwentysixth 1013\n")
            with self.assertRaises(ValueError):
                audit_external_recovery(*a)

    def test_unrequested_attack_edge_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            a[14].write_text(a[14].read_text().replace("Z x\n","Z c\n",1))
            with self.assertRaises(ValueError):
                audit_external_recovery(*a)

    def test_outer_crc_corrupt_recovered_slot_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            raw=bytearray(a[2].read_bytes())
            raw[48]^=0x80
            a[2].write_bytes(raw)
            with self.assertRaises(ValueError):
                audit_external_recovery(*a)

    def test_restored_field_map_must_be_identical(self):
        with tempfile.TemporaryDirectory() as d:
            a=fixture(d)
            path=a[0]/"01_twentyfifth_after_retreat.png"
            with Image.open(path) as im:
                img=im.convert("RGB")
            img.putpixel(screen_point(600,350),(0,232,30))
            img.save(path)
            r=audit_external_recovery(*a)
            self.assertFalse(r["checks"][
                "twentyfifth_retreat_returns_unmodified_original_field"])


if __name__ == "__main__":
    unittest.main()
