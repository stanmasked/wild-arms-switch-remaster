"""Apply and compile the Stage536 PCSX-Redux QueueElement patch on a tiny source excerpt.

This verifies patch mechanics and intended field semantics only. It does not
build PCSX-Redux or run the original Wild Arms disc.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/pcsx-redux/stage536-zero-inactive-cdrom-queue-element.patch"
FIXTURE = ROOT / "tests/stage536_queue_element_prepatch_excerpt.h"

HARNESS = r'''#include <cstdint>
#include <string_view>
using std::uint8_t;
enum class Cause : uint8_t { DataReady = 1 };
#include "src/core/cdrom.h"

int main() {
    QueueElement a;
    QueueElement b;
    if (a.value != 0 || b.value != 0 || a.hitMax || b.hitMax) return 1;
    for (unsigned i = 0; i < 16; ++i) {
        if (a.payload[i] != 0 || b.payload[i] != 0) return 2;
    }

    a.setValue(Cause::DataReady);
    a.pushPayloadData(0x22);
    if (a.value != 1 || !a.hasValue || a.payloadSize != 1 || a.payload[0] != 0x22) return 3;
    for (unsigned i = 1; i < 16; ++i) if (a.payload[i] != 0) return 4;
    if (a.readPayloadByte() != 0x22 || !a.hitMax || !a.isPayloadEmpty()) return 5;

    // Simulate stale bytes and a consumed queue, then exercise clear + reuse.
    a.payload[8] = 0xa5;
    a.payload[9] = 0x5a;
    a.value = 0xff;
    a.valueRead = true;
    a.hasValue = true;
    a.payloadIndex = 1;
    a.clear();
    if (a.value != 0 || a.valueRead || a.hasValue || a.hitMax || a.payloadSize || a.payloadIndex) return 6;
    for (unsigned i = 0; i < 16; ++i) if (a.payload[i] != 0) return 7;
    a.setValue(Cause::DataReady);
    a.pushPayloadData(0x22);
    if (a.isPayloadEmpty() || a.readPayloadByte() != 0x22 || !a.isPayloadEmpty()) return 8;
    a.clear();
    a.pushPayloadData(0x44);
    if (a.isPayloadEmpty() || a.payload[0] != 0x44 || a.payload[1] != 0) return 9;
    return 0;
}
'''


class Stage536QueueElementFixTests(unittest.TestCase):
    def test_patch_is_pinned_to_expected_upstream_blob_and_has_complete_reset(self):
        patch = PATCH.read_text(encoding="utf-8")
        self.assertIn("Expected original src/core/cdrom.h blob: e82969125b2d330420a6d2793e53ddd403fbe43", patch)
        self.assertIn("uint8_t payload[16] = {};", patch)
        self.assertIn("uint8_t value = 0;", patch)
        self.assertIn("for (auto &byte : payload) byte = 0;", patch)
        self.assertIn("hitMax = false;", patch)
        self.assertIn("value = 0;", patch)

    def test_patch_applies_cleanly_and_compiles_semantics_harness(self):
        if not shutil.which("git") or not shutil.which("c++"):
            self.skipTest("requires standard git utility and C++ compiler")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "src/core/cdrom.h"
            target.parent.mkdir(parents=True)
            fixture_text = FIXTURE.read_text(encoding="utf-8")
            # Align the excerpt with the exact upstream QueueElement line numbers.
            excerpt = fixture_text[fixture_text.index("    struct QueueElement {"):]
            target.write_text("// omitted upstream context\n" * 179 + excerpt, encoding="utf-8")
            dry = subprocess.run(["git", "apply", "--check", "--unsafe-paths", str(PATCH)],
                                 cwd=root, text=True, capture_output=True)
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
            applied = subprocess.run(["git", "apply", "--unsafe-paths", str(PATCH)],
                                     cwd=root, text=True, capture_output=True)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            harness = root / "stage536_harness.cpp"
            harness.write_text(HARNESS, encoding="utf-8")
            binary = root / "stage536_harness"
            compiled = subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
                                       "-I", str(root), str(harness), "-o", str(binary)],
                                      cwd=root, text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            run = subprocess.run([str(binary)], cwd=root, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_prepatch_fixture_reproduces_uninitialized_tail_shape(self):
        source = FIXTURE.read_text(encoding="utf-8")
        self.assertIn("uint8_t payload[16];", source)
        self.assertIn("uint8_t value;", source)
        clear = source.split("void clear() {", 1)[1].split("}", 1)[0]
        self.assertNotIn("hitMax = false", clear)
        self.assertNotIn("payload) byte", clear)


if __name__ == "__main__":
    unittest.main()
