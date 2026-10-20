#!/usr/bin/env python3
"""Stage384: invoke the REAL offline recovery CLI in separate OS processes.

The prior 38 Python unit tests exercise the function in the current process.
These tests check argument parsing, exit codes, stdout, and on-disk effects.
All fixtures are synthetic asset-free WABJ records in temporary directories.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_stage_verified_battle_backup import fixture

CLI = Path(__file__).with_name("stage_verified_battle_backup.py")


def invoke(inputs, *extra):
    damaged_a, damaged_b, backup_a, backup_b, sha_a, sha_b, output = inputs
    cmd = [
        sys.executable, str(CLI),
        "--damaged-a", str(damaged_a), "--damaged-b", str(damaged_b),
        "--backup-a", str(backup_a), "--backup-b", str(backup_b),
        "--sha256-a", sha_a, "--sha256-b", sha_b,
        "--output-dir", str(output), *extra,
    ]
    return subprocess.run(
        cmd, cwd=Path(__file__).parent.parent,
        capture_output=True, text=True, timeout=20, check=False)


class RecoveryCliProcessTests(unittest.TestCase):
    def test_real_cli_preview_does_not_create_recovery_directory(self):
        with tempfile.TemporaryDirectory() as d:
            args = fixture(d)
            before = [p.read_bytes() for p in args[:4]]
            proc = invoke(args)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual((result["mode"], result["staged"]),
                             ("dry-run", False))
            self.assertEqual(result["recovered"]["generation"], 6)
            self.assertEqual((result["recovered"]["wins"],
                              result["recovered"]["experience"],
                              result["recovered"]["gella"]), (4, 32, 48))
            self.assertFalse(args[-1].exists())
            self.assertEqual([p.read_bytes() for p in args[:4]], before)

    def test_real_cli_explicit_publish_pins_bytes_without_live_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            args = fixture(d)
            before = [p.read_bytes() for p in args[:4]]
            proc = invoke(args, "--execute")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            response = json.loads(proc.stdout)
            self.assertEqual((response["mode"], response["staged"]),
                             ("explicit-staging", True))
            output = args[-1]
            self.assertEqual({f.name for f in output.iterdir()},
                             {"battle-progress.a", "recovery-manifest.json"})
            self.assertEqual((output / "battle-progress.a").read_bytes(), before[3])
            manifest = json.loads((output / "recovery-manifest.json").read_text())
            self.assertEqual(manifest["verified_backup_sha256"],
                             hashlib.sha256(before[3]).hexdigest())
            self.assertEqual(manifest["corrupt_a_sha256"],
                             hashlib.sha256(before[0]).hexdigest())
            self.assertEqual(manifest["corrupt_b_sha256"],
                             hashlib.sha256(before[1]).hexdigest())
            self.assertEqual(manifest["requires_explicit_restore_by_owner"], True)
            self.assertEqual(manifest["installed_to_live_sdmc"], False)
            self.assertEqual([p.read_bytes() for p in args[:4]], before)

    def test_real_cli_never_overwrites_previous_staged_output(self):
        with tempfile.TemporaryDirectory() as d:
            args = fixture(d)
            first = invoke(args, "--execute")
            self.assertEqual(first.returncode, 0, first.stderr)
            before = {p.name: p.read_bytes() for p in args[-1].iterdir()}
            sources = [p.read_bytes() for p in args[:4]]
            second = invoke(args, "--execute")
            self.assertEqual(second.returncode, 2)
            self.assertIn("already exists", second.stderr)
            self.assertEqual(before,
                             {p.name: p.read_bytes() for p in args[-1].iterdir()})
            self.assertEqual([p.read_bytes() for p in args[:4]], sources)

    def test_real_cli_wrong_sha_refuses_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            args = list(fixture(d))
            args[5] = "0" * 64
            before = [p.read_bytes() for p in args[:4]]
            proc = invoke(args, "--execute")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("pinned SHA-256", proc.stderr)
            self.assertFalse(args[-1].exists())
            self.assertEqual([p.read_bytes() for p in args[:4]], before)

    def test_real_cli_valid_live_source_refuses_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            args = fixture(d)
            args[0].write_bytes(args[2].read_bytes())
            before = [p.read_bytes() for p in args[:4]]
            proc = invoke(args, "--execute")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("live save is still valid", proc.stderr)
            self.assertFalse(args[-1].exists())
            self.assertEqual([p.read_bytes() for p in args[:4]], before)


if __name__ == "__main__":
    unittest.main()
