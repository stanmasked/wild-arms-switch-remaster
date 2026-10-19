#!/usr/bin/env python3
"""Two OS processes, one real journal on disk; no shared C++ state.

Invoked by CTest with the compiled host executable. Includes corrupted
save and stale .tmp negative checks with process boundaries.
"""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# This file is also discovered by the repository-wide Python unittest
# runner, which has not built the C++ helper. Only run the subprocess tests
# when CTest supplies the actual compiled executable argument.
EXECUTABLE = None
if len(sys.argv) == 2:
    candidate = Path(sys.argv[1]).resolve()
    if candidate.is_file() and candidate.name.startswith("wa_field_save_process"):
        EXECUTABLE = candidate
        sys.argv[1:] = []


@unittest.skipUnless(EXECUTABLE is not None, "requires compiled C++ field process executable")
class ProcessRestartTests(unittest.TestCase):
    def invoke(self, mode, path, expected):
        proc = subprocess.run(
            [str(EXECUTABLE), mode, str(path)],
            capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.strip(), expected)
        return proc

    def test_persistent_checkpoint_survives_fresh_os_process(self):
        with tempfile.TemporaryDirectory(prefix="wild-arms-restart-") as td:
            path = Path(td) / "field-save"
            self.invoke("save", path, "FIRST_PROCESS_WRITTEN_PENDING_EVENT")
            payload = path.with_suffix(".a").read_bytes()
            self.assertEqual(len(payload), 56)
            self.assertEqual(payload[:4], b"WAJ1")
            self.assertEqual(payload[4:12], bytes([1,0,0,0,0,0,0,0]))
            digest = hashlib.sha256(payload).hexdigest()
            # No in-process C++ variables can carry into the second invocation.
            self.invoke("load", path,
                        "SECOND_PROCESS_LOADED_AND_ACKNOWLEDGED_EVENT")
            self.assertEqual(hashlib.sha256(
                path.with_suffix(".a").read_bytes()).hexdigest(), digest)

    def test_crash_stale_tmp_never_accepted_in_fresh_process(self):
        with tempfile.TemporaryDirectory(prefix="wild-arms-restart-") as td:
            path = Path(td) / "field-save"
            path.with_suffix(".a.tmp").write_bytes(b"WAJ1" + b"\x00"*20)
            self.invoke("expect-bad", path,
                        "FRESH_PROCESS_REJECTED_BROKEN_FILE_UNCHANGED")
            self.invoke("save", path, "FIRST_PROCESS_WRITTEN_PENDING_EVENT")
            self.invoke("load", path,
                        "SECOND_PROCESS_LOADED_AND_ACKNOWLEDGED_EVENT")

    def test_torn_committed_record_fails_without_state_change(self):
        with tempfile.TemporaryDirectory(prefix="wild-arms-restart-") as td:
            path = Path(td) / "field-save"
            self.invoke("save", path, "FIRST_PROCESS_WRITTEN_PENDING_EVENT")
            damaged = bytearray(path.with_suffix(".a").read_bytes())
            damaged[23] ^= 0xFF
            path.with_suffix(".a").write_bytes(damaged)
            self.invoke("expect-bad", path,
                        "FRESH_PROCESS_REJECTED_BROKEN_FILE_UNCHANGED")


if __name__ == "__main__":
    unittest.main()
