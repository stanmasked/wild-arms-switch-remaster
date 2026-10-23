"""Stage493: validate the pinned GP0(00h) NOP compatibility patch."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from patch_private_pcsx_gpu_gp0_nop import (
    PINNED, OLD_CASE, NEW_CASE, patched_gpu_source, make_diff,
)

GPU_SOURCE_SNIPPET = """void PCSX::GPU::Command::processWrite(Buffer &buf, Logged::Origin origin, uint32_t originValue, uint32_t length) {
    while (!buf.isEmpty()) {
        uint32_t value = buf.get();
        bool gotUnknown = false;
        const uint8_t cmdType = value >> 29;
        const uint8_t command = (value >> 24) & 0x1f;
        switch (cmdType) {
            case 0:
                switch (command) {
                    case 0x01: {  // clear cache
                        ClearCache prim;
                        m_gpu->write0(&prim);
                    } break;
                    default: {
                        gotUnknown = true;
                    } break;
                }
                break;
        }
        if (gotUnknown && (value != 0)) {
            g_system->log(LogClass::GPU, "Got an unknown GPU data word: %08x (cmdType: %hhu, command: %hhu)\\n", value,
                          cmdType, command);
        }
    }
}
"""


class Stage493GP0NopPatchTests(unittest.TestCase):
    def test_pinned_upstream_revision_is_exact(self):
        self.assertEqual(PINNED, "de4a33e9a69abec4f567ae33567537f867dc2bba")

    def test_address_shaped_command_zero_is_explicitly_a_nop(self):
        value = 0x000326cc
        self.assertEqual(value >> 29, 0)
        self.assertEqual((value >> 24) & 0x1f, 0)
        patched = patched_gpu_source(GPU_SOURCE_SNIPPET)
        self.assertIn(NEW_CASE, patched)
        self.assertLess(patched.index("case 0x00:"), patched.index("case 0x01:"))
        self.assertIn("if (gotUnknown && (value != 0))", patched)

    def test_patch_fails_closed_when_anchor_is_missing_or_duplicated(self):
        with self.assertRaisesRegex(ValueError, "anchor absent or duplicated"):
            patched_gpu_source("void processWrite() {}")
        with self.assertRaisesRegex(ValueError, "anchor absent or duplicated"):
            patched_gpu_source(GPU_SOURCE_SNIPPET + "\\n" + OLD_CASE)

    def test_generated_diff_only_targets_gpu_source(self):
        diff = make_diff(GPU_SOURCE_SNIPPET)
        self.assertIn("--- a/src/core/gpu.cc", diff)
        self.assertIn("+++ b/src/core/gpu.cc", diff)
        self.assertNotIn("src/core/gpudump.cc", diff)
        self.assertIn("+                    case 0x00:", diff)

    def test_diff_applies_to_clean_synthetic_checkout(self):
        git = shutil.which("git")
        if git is None:
            self.skipTest("git executable not installed")
        diff = make_diff(GPU_SOURCE_SNIPPET)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src/core/gpu.cc"
            source.parent.mkdir(parents=True)
            source.write_text(GPU_SOURCE_SNIPPET, encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run([
                "git", "-C", str(root), "-c", "user.name=Stage493",
                "-c", "user.email=stage493@example.invalid", "commit", "-qm",
                "synthetic pristine GPU source",
            ], check=True)
            checked = subprocess.run(
                ["git", "-C", str(root), "apply", "--check", "-"],
                input=diff, capture_output=True, text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            applied = subprocess.run(
                ["git", "-C", str(root), "apply", "-"],
                input=diff, capture_output=True, text=True,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            changed = source.read_text(encoding="utf-8")
            self.assertIn(NEW_CASE, changed)
            self.assertEqual(changed.count("case 0x00:"), 1)


if __name__ == "__main__":
    unittest.main()
