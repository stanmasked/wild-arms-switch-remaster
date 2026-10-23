#!/usr/bin/env python3
"""Generate/apply a narrow GP0(00h) NOP compatibility patch to pinned PCSX-Redux.

The low 24 bits of GP0 command 00h are ignored by the PS1 GPU. This patch
prevents address-shaped low bits from being misreported as an unknown command.
It changes emulator command decoding only; no game assets or BIOS are included.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

PINNED = "de4a33e9a69abec4f567ae33567537f867dc2bba"
GPU_SOURCE = "src/core/gpu.cc"

OLD_CASE = """                switch (command) {
                    case 0x01: {  // clear cache"""
NEW_CASE = """                switch (command) {
                    case 0x00: {  // GP0(00h) NOP; the low 24 bits are ignored.
                        // Address-shaped payload bits are not an unknown command.
                    } break;
                    case 0x01: {  // clear cache"""


def replace_once(source, needle, replacement):
    if source.count(needle) != 1:
        raise ValueError("pinned upstream GPU command anchor absent or duplicated")
    return source.replace(needle, replacement, 1)


def patched_gpu_source(source):
    return replace_once(source, OLD_CASE, NEW_CASE)


def make_diff(source):
    changed = patched_gpu_source(source)
    return "".join(difflib.unified_diff(
        source.splitlines(keepends=True),
        changed.splitlines(keepends=True),
        fromfile="a/" + GPU_SOURCE,
        tofile="b/" + GPU_SOURCE,
    ))


def check_or_apply(repository, apply=False):
    repository = Path(repository)
    if not repository.is_dir():
        raise ValueError("PCSX-Redux directory not found")
    pinned = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if pinned != PINNED:
        raise ValueError("refusing unpinned PCSX-Redux checkout: " + pinned)
    for args in (
        ["diff", "--quiet", "--", GPU_SOURCE],
        ["diff", "--cached", "--quiet", "--", GPU_SOURCE],
    ):
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise ValueError("refusing already-modified GPU source: " + GPU_SOURCE)
    source_path = repository / GPU_SOURCE
    source = source_path.read_text(encoding="utf-8")
    patch = make_diff(source)
    if not patch:
        raise ValueError("empty GP0 NOP compatibility patch")
    checked = subprocess.run(
        ["git", "-C", str(repository), "apply", "--check", "-"],
        input=patch, capture_output=True, text=True,
    )
    if checked.returncode:
        raise ValueError("generated GP0 NOP patch rejected: " + checked.stderr[:700])
    if apply:
        subprocess.run(
            ["git", "-C", str(repository), "apply", "-"],
            input=patch, check=True, capture_output=True, text=True,
        )
    return patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_redux_checkout")
    parser.add_argument("--apply", action="store_true",
                        help="Modify the owner's pinned checkout")
    args = parser.parse_args()
    patch = check_or_apply(args.pinned_pcsx_redux_checkout, args.apply)
    print(("Applied" if args.apply else "Validated") +
          " pinned GP0(00h) NOP compatibility patch; diff size " +
          str(len(patch.encode("utf-8"))) + " bytes.")


if __name__ == "__main__":
    main()
