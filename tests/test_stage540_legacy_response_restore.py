"""Stage540 ROM-free compatibility guard for legacy, inactive CD-ROM response FIFOs.

Tests only a generated C++ excerpt. It does not load copyrighted game data
or claim that a complete emulator/game replay has passed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/pcsx-redux/stage540-normalize-legacy-inactive-response.patch"


def run_checked(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"{args}: {result.stdout}\n{result.stderr}")
    return result.stdout


class Stage540RestoreGuardTests(unittest.TestCase):
    def test_patch_contains_only_post_restore_hook_and_empty_fifo_guard(self):
        source = PATCH.read_text(encoding="utf-8")
        self.assertIn("de4a33e9a69abec4f567ae33567537f867dc2bba", source)
        self.assertIn("if (!fifo.hasValue && !fifo.valueRead && !fifo.hitMax && fifo.payloadSize == 0 &&", source)
        self.assertIn("fifo.clear();", source)
        self.assertIn("state.commit();", source)
        self.assertIn("g_emulator->m_cdrom->normalizeRestoredResponseQueues();", source)
        self.assertEqual(source.count("--- a/"), 2)

    def test_synthetic_header_applies_and_preserves_live_fifo(self):
        if not shutil.which("git") or not shutil.which("c++"):
            self.skipTest("requires git and C++17 compiler")

        with tempfile.TemporaryDirectory(prefix="stage540-romfree-") as tmp:
            root = Path(tmp)
            (root / "src/core").mkdir(parents=True)
            header = root / "src/core/cdrom.h"
            header.write_text(
                "#include <cstdint>\nclass CDRom {\npublic:\n"
                + "// synthetic padding\n" * 76
                + "    virtual void reset() = 0;\n\n"
                  "    virtual void fifoScheduledCallback() = 0;\n"
                  "protected:\n"
                  "    struct QueueElement {\n"
                  "        uint8_t payload[16] = {};\n"
                  "        uint8_t value = 0;\n"
                  "        bool valueRead = false;\n"
                  "        bool hasValue = false;\n"
                  "        bool hitMax = false;\n"
                  "        uint8_t payloadSize = 0;\n"
                  "        uint8_t payloadIndex = 0;\n"
                  "        void clear() {\n"
                  "            for (auto& byte : payload) byte = 0;\n"
                  "            value = 0; hasValue = false; valueRead = false;\n"
                  "            hitMax = false; payloadSize = 0; payloadIndex = 0;\n"
                  "        }\n"
                  "    };\n"
                  "    QueueElement m_responseFifo[2];\n"
                  "};\n",
                encoding="utf-8",
            )
            state = root / "src/core/sstate.cc"
            prelude = '#include "cdrom.h"\nstruct CPU { void invalidateCache() {};\n'
            prelude += " struct Regs { int cycle = 0; int lowestTarget = 0; } m_regs; };\n"
            prelude += "struct Emu { CPU* m_cpu; CDRom* m_cdrom; };\n"
            prelude += "extern Emu* g_emulator;\n"
            prelude += "struct State { void commit() {} };\n"
            prelude += "void restore(State& state) {\n"
            count = prelude.count("\n") + 1
            state.write_text(
                prelude + "// synthetic padding\n" * (303-count)
                + "    g_emulator->m_cpu->invalidateCache();\n"
                  "    state.commit();\n"
                  "    g_emulator->m_cpu->m_regs.lowestTarget = g_emulator->m_cpu->m_regs.cycle;\n"
                  "}\n",
                encoding="utf-8",
            )
            self.assertEqual(header.read_text().splitlines()[79], "    virtual void reset() = 0;")
            self.assertEqual(state.read_text().splitlines()[302], "    g_emulator->m_cpu->invalidateCache();")
            run_checked(["git", "apply", "--check", "--unsafe-paths", str(PATCH)], root)
            run_checked(["git", "apply", "--unsafe-paths", str(PATCH)], root)

            text = state.read_text()
            self.assertLess(text.index("state.commit();"), text.index("normalizeRestoredResponseQueues();"))

            main = root / "test.cpp"
            main.write_text(
                '#include "src/core/cdrom.h"\n'
                "struct TestCD : CDRom {\n"
                " void reset() override {} void fifoScheduledCallback() override {}\n"
                " int check() {\n"
                "  // First FIFO: active one-byte DataReady payload must survive.\n"
                "  m_responseFifo[0].hasValue = true;\n"
                "  m_responseFifo[0].payloadSize = 1;\n"
                "  m_responseFifo[0].payload[0] = 0x22;\n"
                "  // Second FIFO: old serialized garbage with no active metadata.\n"
                "  m_responseFifo[1].value = 1;\n"
                "  m_responseFifo[1].payload[0] = 0x22;\n"
                "  m_responseFifo[1].payload[8] = 0x37;\n"
                "  normalizeRestoredResponseQueues();\n"
                "  if (m_responseFifo[0].payload[0] != 0x22 || !m_responseFifo[0].hasValue) return 1;\n"
                "  if (m_responseFifo[1].payload[0] || m_responseFifo[1].payload[8] || m_responseFifo[1].value) return 2;\n"
                "  // A pending payload is never normalized away, even with hasValue=false.\n"
                "  m_responseFifo[1].payloadSize = 1;\n"
                "  m_responseFifo[1].payload[0] = 0x44;\n"
                "  normalizeRestoredResponseQueues();\n"
                "  if (m_responseFifo[1].payload[0] != 0x44 || m_responseFifo[1].payloadSize != 1) return 3;\n"
                "  // A consumed/marked FIFO is conservatively retained.\n"
                "  m_responseFifo[1].payloadSize = 0;\n"
                "  m_responseFifo[1].hitMax = true;\n"
                "  m_responseFifo[1].payload[0] = 0x55;\n"
                "  normalizeRestoredResponseQueues();\n"
                "  if (m_responseFifo[1].payload[0] != 0x55) return 4;\n"
                "  return 0;\n"
                " }\n"
                "};\n"
                "int main() { TestCD cd; return cd.check(); }\n",
                encoding="utf-8",
            )
            run_checked(
                ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I", ".",
                 "test.cpp", "-o", "test"],
                root,
            )
            run_checked([str(root / "test")], root)


if __name__ == "__main__":
    unittest.main()
