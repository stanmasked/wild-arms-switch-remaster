#!/usr/bin/env python3
"""Stage371 offline recovery integrity tests (synthetic input; not guest proof)."""
import hashlib
import json
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from stage_verified_battle_backup import prepare_recovery, _journal_from_bytes
from test_audit_nexium_battle_two_victories import journal


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def fixture(root):
    root = Path(root)
    (root / "live-save").mkdir()
    (root / "independent-backups").mkdir()
    good_a = root / "independent-backups" / "separate-external-gen5.a"
    good_b = root / "independent-backups" / "separate-external-gen6.b"
    bad_a = root / "live-save" / "damaged-live.a"
    bad_b = root / "live-save" / "damaged-live.b"
    journal(good_a, 5, 1, 4, 1, 32, 48)
    journal(good_b, 6, 3, 4, 2, 32, 48)
    for src, dest in ((good_a, bad_a), (good_b, bad_b)):
        data = bytearray(src.read_bytes())
        data[48] ^= 0x80
        dest.write_bytes(data)
    return (bad_a, bad_b, good_a, good_b, digest(good_a.read_bytes()),
            digest(good_b.read_bytes()), root / "new-isolated-recovery")


def call(a, execute=False):
    return prepare_recovery(*a, execute=execute)


class SafeOfflineRecoveryTests(unittest.TestCase):
    def test_preview_does_not_create_any_files(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            before = [p.read_bytes() for p in a[:4]]
            r = call(a)
            self.assertFalse(a[-1].exists())
            self.assertEqual(r["recovered"]["generation"], 6)
            self.assertEqual(r["recovered"]["wins"], 4)
            self.assertEqual(r["recovered"]["retreats"], 2)
            self.assertEqual((r["recovered"]["experience"], r["recovered"]["gella"]), (32, 48))
            self.assertEqual([p.read_bytes() for p in a[:4]], before)

    def test_explicit_staging_preserves_all_inputs_and_recovers_gen6(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            before = [p.read_bytes() for p in a[:4]]
            r = call(a, execute=True)
            self.assertTrue(r["staged"])
            self.assertEqual(sorted(x.name for x in a[-1].iterdir()),
                             ["battle-progress.a", "recovery-manifest.json"])
            restored = a[-1] / "battle-progress.a"
            self.assertEqual(restored.read_bytes(), before[3])
            self.assertEqual(_journal_from_bytes(restored.read_bytes())["generation"], 6)
            self.assertEqual([p.read_bytes() for p in a[:4]], before)
            manifest = json.loads((a[-1] / "recovery-manifest.json").read_text())
            self.assertFalse(manifest["installed_to_live_sdmc"])
            self.assertEqual(manifest["backup_used"], "b")
            self.assertEqual(manifest["recovered"]["gella"], 48)

    def test_new_output_is_not_a_live_install(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            call(a, execute=True)
            self.assertFalse((a[-1] / "battle-progress.b").exists())
            self.assertTrue(a[0].exists() and a[1].exists())

    def test_older_backup_only_can_be_selected_explicitly(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[3] = None
            a[5] = None
            r = call(a, execute=True)
            self.assertEqual(r["backup_used"], "a")
            self.assertEqual(r["recovered"]["generation"], 5)

    def test_latest_backup_only(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[2] = None
            a[4] = None
            r = call(a)
            self.assertEqual(r["backup_used"], "b")
            self.assertEqual(r["recovered"]["generation"], 6)

    def test_missing_both_backups_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[2] = a[3] = a[4] = a[5] = None
            with self.assertRaises(ValueError):
                call(a)

    def test_missing_backup_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[4] = None
            with self.assertRaises(ValueError):
                call(a)

    def test_malformed_backup_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[5] = "00" * 31
            with self.assertRaises(ValueError):
                call(a)

    def test_modified_but_valid_backup_needs_independent_hash(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            journal(a[3], 6, 3, 4, 3, 32, 48)
            with self.assertRaises(ValueError):
                call(a)

    def test_corrupt_inner_WABR_checksum_fails_even_with_updated_sha(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            data = bytearray(a[3].read_bytes())
            data[44] ^= 0x01
            a[3].write_bytes(data)
            a[5] = digest(data)
            with self.assertRaises(ValueError):
                call(a)

    def test_corrupt_outer_WABJ_checksum_fails_even_with_updated_sha(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            data = bytearray(a[3].read_bytes())
            data[48] ^= 0x01
            a[3].write_bytes(data)
            a[5] = digest(data)
            with self.assertRaises(ValueError):
                call(a)

    def test_invalid_semantic_outcome_fails_even_with_new_crc(self):
        import struct
        import zlib
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            data = bytearray(a[3].read_bytes())
            data[17] = 0  # LAST outcome NONE with nonzero counters
            struct.pack_into("<I", data, 44, zlib.crc32(data[12:44]))
            struct.pack_into("<I", data, 48, zlib.crc32(data[:48]))
            a[3].write_bytes(data)
            a[5] = digest(data)
            with self.assertRaises(ValueError):
                call(a)

    def test_equally_generated_conflicting_backups_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            journal(a[3], 5, 3, 4, 2, 32, 48)
            a[5] = digest(a[3].read_bytes())
            with self.assertRaises(ValueError):
                call(a)

    def test_newer_generation_cannot_regress_earned_rewards(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            journal(a[3], 6, 3, 4, 2, 16, 24)
            a[5] = digest(a[3].read_bytes())
            with self.assertRaises(ValueError):
                call(a)

    def test_valid_current_live_slot_must_not_be_rewritten(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            shutil.copyfile(a[2], a[0])
            with self.assertRaises(ValueError):
                call(a)

    def test_existing_destination_always_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            a[-1].mkdir()
            marker = a[-1] / "personal.txt"
            marker.write_text("do not overwrite")
            with self.assertRaises(FileExistsError):
                call(a, execute=True)
            self.assertEqual(marker.read_text(), "do not overwrite")

    def test_symlink_destination_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            target = Path(d) / "elsewhere"
            target.mkdir()
            a[-1].symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError):
                call(a, execute=True)
            self.assertEqual(list(target.iterdir()), [])

    def test_symlink_backup_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            link = Path(d) / "linked.a"
            link.symlink_to(a[2])
            a[2] = link
            with self.assertRaises(ValueError):
                call(a)

    def test_hardlinked_live_and_backup_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[2].unlink()
            import os
            os.link(a[0], a[2])
            with self.assertRaises(ValueError):
                call(a)

    def test_staging_beside_corrupt_live_saves_is_forbidden_even_in_preview(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            a[-1] = a[0].parent / "accidental-live-recovery"
            before = [p.read_bytes() for p in a[:4]]
            for execute in (False, True):
                with self.assertRaisesRegex(ValueError, "outside live save"):
                    call(a, execute=execute)
            self.assertFalse(a[-1].exists())
            self.assertEqual([p.read_bytes() for p in a[:4]], before)

    def test_nested_live_save_subdirectory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            inside = a[0].parent / "old-copies"
            inside.mkdir()
            a[-1] = inside / "new-package"
            with self.assertRaisesRegex(ValueError, "outside live save"):
                call(a, execute=True)
            self.assertEqual(list(inside.iterdir()), [])

    def test_symlinked_parent_into_live_save_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = list(fixture(d))
            link = Path(d) / "looks-safe"
            link.symlink_to(a[0].parent, target_is_directory=True)
            a[-1] = link / "accidental-package"
            with self.assertRaisesRegex(ValueError, "outside live save"):
                call(a, execute=True)
            self.assertFalse((a[0].parent / "accidental-package").exists())

    def test_sibling_external_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            result = call(a, execute=True)
            self.assertTrue(result["staged"])
            self.assertTrue((a[-1] / "recovery-manifest.json").is_file())

    def test_failed_publication_leaves_no_incomplete_output(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            originals = [p.read_bytes() for p in a[:4]]
            with mock.patch("stage_verified_battle_backup._publish_exclusive",
                            side_effect=OSError("simulated publication failure")):
                with self.assertRaises(OSError):
                    call(a, execute=True)
            self.assertFalse(a[-1].exists())
            self.assertFalse(list(Path(d).glob(".wild-arms-stage371-*")))
            self.assertEqual([p.read_bytes() for p in a[:4]], originals)

    def test_staged_publication_fsyncs_parent_after_directory_rename(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            original_fsync = os.fsync
            calls = []
            def track(fd):
                calls.append(fd)
                return original_fsync(fd)
            with mock.patch("stage_verified_battle_backup.os.fsync", new=track):
                result = call(a, execute=True)
            self.assertTrue(result["staged"])
            # Two output files, staging directory, then destination parent.
            self.assertEqual(len(calls), 4)

    def test_failed_parent_directory_fsync_reports_failure_without_erasing_package(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            before = [p.read_bytes() for p in a[:4]]
            original_fsync = os.fsync
            count = [0]
            def fail_at_parent(fd):
                count[0] += 1
                if count[0] == 4:
                    raise OSError("simulated parent directory durability failure")
                return original_fsync(fd)
            with mock.patch("stage_verified_battle_backup.os.fsync", new=fail_at_parent):
                with self.assertRaisesRegex(OSError, "durability failure"):
                    call(a, execute=True)
            self.assertEqual(count[0], 4)
            # The already published package must not be silently deleted
            # or reported as durably complete after the failed fsync.
            self.assertEqual(sorted(p.name for p in a[-1].iterdir()),
                             ["battle-progress.a", "recovery-manifest.json"])
            self.assertEqual((a[-1] / "battle-progress.a").read_bytes(), before[3])
            self.assertEqual([p.read_bytes() for p in a[:4]], before)

    def test_competing_new_destination_must_not_be_replaced(self):
        from stage_verified_battle_backup import _publish_exclusive
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            def race(stage, destination):
                Path(destination).mkdir()
                (Path(destination) / "owner-data.txt").write_text(
                    "belongs to someone else")
                return _publish_exclusive(stage, destination)
            with mock.patch("stage_verified_battle_backup._publish_exclusive",
                            new=race):
                with self.assertRaises(FileExistsError):
                    call(a, execute=True)
            self.assertEqual((a[-1] / "owner-data.txt").read_text(),
                             "belongs to someone else")
            self.assertFalse(list(Path(d).glob(".wild-arms-stage371-*")))

    def test_competing_empty_directory_is_not_replaced(self):
        from stage_verified_battle_backup import _publish_exclusive
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            def race(stage, destination):
                Path(destination).mkdir()
                return _publish_exclusive(stage, destination)
            with mock.patch("stage_verified_battle_backup._publish_exclusive",
                            new=race):
                with self.assertRaises(FileExistsError):
                    call(a, execute=True)
            self.assertTrue(a[-1].is_dir())
            self.assertEqual(list(a[-1].iterdir()), [])
            self.assertFalse(list(Path(d).glob(".wild-arms-stage371-*")))

    def test_competing_symlink_destination_is_not_replaced(self):
        from stage_verified_battle_backup import _publish_exclusive
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            target = Path(d) / "other-owner"
            target.mkdir()
            (target / "keep.txt").write_text("independent")
            def race(stage, destination):
                Path(destination).symlink_to(target, target_is_directory=True)
                return _publish_exclusive(stage, destination)
            with mock.patch("stage_verified_battle_backup._publish_exclusive",
                            new=race):
                with self.assertRaises(FileExistsError):
                    call(a, execute=True)
            self.assertTrue(a[-1].is_symlink())
            self.assertEqual((target / "keep.txt").read_text(), "independent")
            self.assertFalse(list(Path(d).glob(".wild-arms-stage371-*")))

    def test_swapped_symlink_during_source_open_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            target = a[3]
            parked = target.with_suffix(".parked")
            original_open = os.open
            was_swapped = [False]
            def swap(path, flags, *args, **kwargs):
                if Path(path) == target and not was_swapped[0]:
                    was_swapped[0] = True
                    target.rename(parked)
                    target.symlink_to(a[0])
                return original_open(path, flags, *args, **kwargs)
            with mock.patch("stage_verified_battle_backup.os.open", new=swap):
                with self.assertRaises((ValueError, OSError)):
                    call(a, execute=True)
            self.assertTrue(was_swapped[0])
            self.assertFalse(a[-1].exists())

    def test_stage_does_not_include_an_unverified_second_slot(self):
        with tempfile.TemporaryDirectory() as d:
            a = fixture(d)
            call(a, execute=True)
            files = {x.name for x in a[-1].iterdir()}
            self.assertEqual(files, {"battle-progress.a", "recovery-manifest.json"})
            self.assertNotIn("damaged-live.a", files)


if __name__ == "__main__":
    unittest.main()
