"""Validate the pinned GP0 NOP runtime regression fixture patch."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from patch_private_pcsx_gp0_nop_runtime_test import (
    ANCHOR, PASS_MARKER, RUNTIME_TEST, TEST_NAME, patched_guest_source,
)


class GP0NopRuntimeFixtureTests(unittest.TestCase):
    def test_adds_exact_address_shaped_nop_probe(self):
        source = "/* pinned fixture */\n" + ANCHOR + "\n"
        changed = patched_guest_source(source)
        self.assertEqual(changed.count(TEST_NAME), 1)
        self.assertEqual(changed.count(PASS_MARKER), 1)
        self.assertIn("cmdSend(0x000326ccu);", changed)
        self.assertIn("cester_assert_uint_eq((unsigned)before, (unsigned)after);", changed)

    def test_fails_closed_when_anchor_is_missing_or_duplicated(self):
        with self.assertRaisesRegex(ValueError, "anchor absent or duplicated"):
            patched_guest_source("/* unrelated source */\n")
        with self.assertRaisesRegex(ValueError, "anchor absent or duplicated"):
            patched_guest_source(ANCHOR + "\n" + ANCHOR)

    def test_refuses_to_patch_the_same_fixture_twice(self):
        changed = ANCHOR + "\n" + RUNTIME_TEST
        with self.assertRaisesRegex(ValueError, "already present"):
            patched_guest_source(changed)


if __name__ == "__main__":
    unittest.main()
