#!/usr/bin/env python3
"""Apply pinned CI-only GP0 NOP runtime coverage to the PS1 guest test.

The production compatibility patch remains restricted to src/core/gpu.cc.
This fixture patch also enables stdout for the existing GPU guest-test runner
so the runtime marker and unexpected-command diagnostics are observable.
"""
import argparse
from pathlib import Path
import subprocess

PCSX_PINNED = "de4a33e9a69abec4f567ae33567537f867dc2bba"
MIPS_PINNED = "7f9651226bedd29af6545883db27c9a556d05faa"
GUEST_SOURCE = "src/mips/tests/gpu-command/status.c"
SUBMODULE_SOURCE = "tests/gpu-command/status.c"
HOST_SOURCE = "tests/pcsxrunner/gpu-command.cc"
TEST_NAME = "command_gp0_00_nop_ignores_low_24_bits"
PASS_MARKER = "GP0_NOP_RUNTIME_PROBE_PASS word=000326cc"
HOST_MARKER = 'MainInvoker invoker("-no-ui", "-stdout", "-run"'

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

HOST_ANCHOR = """TEST(GPUCommand, StatusAfterWrite) {
    MainInvoker invoker("-no-ui", "-run", "-bios", "src/mips/openbios/openbios.bin", "-testmode", "-interpreter",
                        "-loadexe", "src/mips/tests/gpu-command/gpu-command.ps-exe");
    int ret = invoker.invoke();
    EXPECT_EQ(ret, 0);
}"""


def patched_guest_source(source):
    if TEST_NAME in source or PASS_MARKER in source:
        raise ValueError("GP0 NOP runtime regression is already present")
    if source.count(ANCHOR) != 1:
        raise ValueError("pinned GPU guest-test anchor absent or duplicated")
    changed = source.replace(ANCHOR, ANCHOR + "\n\n" + RUNTIME_TEST, 1)
    if changed.count(PASS_MARKER) != 1:
        raise ValueError("runtime probe marker validation failed")
    return changed


def patched_host_source(source):
    if HOST_MARKER in source:
        raise ValueError("GPU guest-test stdout flag is already present")
    if source.count(HOST_ANCHOR) != 1:
        raise ValueError("pinned GPU host-runner anchor absent or duplicated")
    changed_anchor = HOST_ANCHOR.replace(
        'MainInvoker invoker("-no-ui", "-run"',
        'MainInvoker invoker("-no-ui", "-stdout", "-run"',
        1,
    )
    changed = source.replace(HOST_ANCHOR, changed_anchor, 1)
    if changed.count(HOST_MARKER) != 1:
        raise ValueError("GPU guest-test stdout flag validation failed")
    return changed


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _require_clean_path(root, path):
    for args in (("diff", "--quiet", "--", path),
                 ("diff", "--cached", "--quiet", "--", path)):
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise ValueError("refusing already-modified source: " + path)


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

    _require_clean_path(submodule, SUBMODULE_SOURCE)
    _require_clean_path(repository, HOST_SOURCE)

    guest_path = repository / GUEST_SOURCE
    host_path = repository / HOST_SOURCE
    guest_changed = patched_guest_source(guest_path.read_text(encoding="utf-8"))
    host_changed = patched_host_source(host_path.read_text(encoding="utf-8"))
    if apply:
        guest_path.write_text(guest_changed, encoding="utf-8")
        host_path.write_text(host_changed, encoding="utf-8")
    return guest_changed, host_changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_redux_checkout")
    parser.add_argument("--apply", action="store_true",
                        help="Patch the pinned guest fixture and its host test runner")
    args = parser.parse_args()
    check_or_apply(args.pinned_pcsx_redux_checkout, args.apply)
    print(("Applied" if args.apply else "Validated") +
          " pinned GP0 NOP runtime regression and stdout-enabled runner.")


if __name__ == "__main__":
    main()
