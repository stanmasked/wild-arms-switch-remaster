#!/usr/bin/env python3
"""Synthetic session log fixtures, never treated as guest execution."""
from pathlib import Path
import tempfile
import unittest

from audit_nexium_session import analyze


class SessionAuditTests(unittest.TestCase):
    def test_missing_both_session_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            result = analyze(base / "missing-g.log", base / "missing-c.log")
            self.assertEqual(result["guest_boot_outcome"], "internal_log_missing")
            self.assertFalse(result["guest_rendered_frame_confirmed"])

    def test_auto_loaded_only_describes_loader_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            guest, control = base / "guest.log", base / "control.log"
            guest.write_text("Boot: NRO=/tmp/sample.nro CPU=dynarmic\n"
                             "Auto-loaded NRO: /tmp/sample.nro (CPU: dynarmic)\n")
            control.write_text("Window GPU: llvmpipe\n")
            result = analyze(guest, control)
            self.assertEqual(result["guest_boot_outcome"], "guest_boot_requested")
            self.assertTrue(result["frontend_autoload_request_seen"])
            self.assertTrue(result["guest_boot_request_seen"])
            self.assertFalse(result["control_has_autoload_marker"])
            self.assertFalse(result["guest_rendered_frame_confirmed"])

    def test_real_ne_xium_loader_bounds_failure_not_false_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            guest = base / "guest.log"
            guest.write_text(
                "Auto-loaded NRO: /tmp/game.nro (CPU: Dynarmic)\n"
                "Booting NRO: /tmp/game.nro\n"
                "[ERROR] Boot failed: Data segment out of bounds\n"
            )
            result = analyze(guest, base / "missing-control.log")
            self.assertEqual(result["guest_boot_outcome"], "guest_boot_failed")
            self.assertTrue(result["guest_boot_failure_reported"])
            self.assertTrue(result["guest_boot_request_seen"])
            self.assertTrue(result["frontend_autoload_request_seen"])
            self.assertFalse(result["guest_rendered_frame_confirmed"])

    def test_explicit_load_failure_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            guest = base / "guest.log"
            guest.write_text("Auto-loaded NRO: /tmp/bad.nro\n"
                             "Failed to load NRO: /tmp/bad.nro\n")
            result = analyze(guest, base / "no-control.log")
            self.assertEqual(result["guest_boot_outcome"], "frontend_load_request_failed")
            self.assertTrue(result["frontend_load_request_failure_seen"])
            self.assertFalse(result["guest_rendered_frame_confirmed"])


if __name__ == "__main__":
    unittest.main()
