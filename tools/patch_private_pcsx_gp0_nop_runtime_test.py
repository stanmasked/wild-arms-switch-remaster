#!/usr/bin/env python3
"""Apply a pinned, CI-only GP0 NOP runtime regression to the PS1 guest test.

This modifies only the upstream MIPS test fixture in the temporary CI checkout.
The production compatibility patch remains restricted to src/core/gpu.cc.
"""
import argparse
from pathlib import Path
import subprocess

PCSX_PINNED = "de4a33e9a69abec4f567ae33567537f867dc2bba"
MIPS_PINNED = "7f9651226bedd29af6545883db27c9a556d05faa"
GUEST_SOURCE = "src/mips/tests/gpu-command/status.c"
SUBMODULE_SOURCE = "tests/gpu-command/status.c"
TEST_NAME = "command_gp0_00_nop_ignores_low_24_bits"
PASS_MARKER = "GP0_NOP_RUNTIME_PROBE_PASS word=000326cc"

ANCHOR = """CESTER_TEST(command_e6_check_mask_reflects_in_gpustat, gpu_command,
    rasterReset();
    cmdSend(0xe6000002u);  // set-mask off, check-mask on
    ASSERT_STAT_EQ(0x1000u, 0x1800u);
)"""

RUNTIME_TEST = """CESTER_TEST(command_gp0_00_nop_ignores_low_24_bits, gpu_command,
    rasterReset();
    cmdSend(0xe10006d5u);
    uint32_t before = GPU_STATUS & 0x7ffu;
    ramsyscall_printf("GP0_NOP_RUNTIME_PROBE_BEGIN word=000326cc\\n");
    cmdSend(0x000326ccu);
    uint32_t after = GPU_STATUS & 0x7ffu;
    ramsyscall_printf("GP0_NOP_RUNTIME_PROBE_PASS word=000326cc before=%08x after=%08x\\n",
                      (unsigned)before, (unsigned)after);
    cester_assert_uint_eq((unsigned)before, (unsigned)after);
)"""


def patched_guest_source(source):
    if TEST_NAME in source or PASS_MARKER in source:
        raise ValueError("GP0 NOP runtime regression is already present")
    if source.count(ANCHOR) != 1:
        raise ValueError("pinned GPU guest-test anchor absent or duplicated")
    return source.replace(ANCHOR, ANCHOR + "\n\n" + RUNTIME_TEST, 1)


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def check_or_apply(repository, apply=False):
    repository = Path(repository).resolve()
    if not repository.is_dir():
        raise ValueError("PCSX-Redux directory not found")
    pinned = _git(repository, "rev-parse", "HEAD")
    if pinned != PCSX_PINNED:
        raise ValueError("refusing unpinned PCSX-Redux checkout: " + pinned)
    submodule = repository / "src/mips"
    mips_sha = _git(submodule, "rev-parse", "HEAD")
    if mips_sha != MIPS_PINNED:
        raise ValueError("refusing unpinned MIPS test submodule: " + mips_sha)

    for args in (
        ("diff", "--quiet", "--", SUBMODULE_SOURCE),
        ("diff", "--cached", "--quiet", "--", SUBMODULE_SOURCE),
    ):
        result = subprocess.run(
            ["git", "-C", str(submodule), *args],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise ValueError("refusing already-modified guest test source: " + SUBMODULE_SOURCE)

    path = repository / GUEST_SOURCE
    source = path.read_text(encoding="utf-8")
    changed = patched_guest_source(source)
    if changed.count(PASS_MARKER) != 1:
        raise ValueError("runtime probe marker validation failed")
    if apply:
        path.write_text(changed, encoding="utf-8")
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_redux_checkout")
    parser.add_argument("--apply", action="store_true",
                        help="Modify the temporary pinned MIPS guest-test fixture")
    args = parser.parse_args()
    check_or_apply(args.pinned_pcsx_redux_checkout, args.apply)
    print(("Applied" if args.apply else "Validated") +
          " pinned GP0 NOP runtime regression guest test.")


if __name__ == "__main__":
    main()
