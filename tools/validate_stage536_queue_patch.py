#!/usr/bin/env python3
"""Check Stage536 QueueElement patch against the exact pinned PCSX-Redux header.

This applies the candidate to a temporary copy of one public upstream header.
It does not modify the fetched checkout, build PCSX-Redux, or run game data.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

PINNED_COMMIT = "de4a33e9a69abec4f567ae33567537f867dc2bba"
PINNED_HEADER_BLOB = "e82969125b2d330420a6d2793e53ddd403fbe43"
HEADER = "src/core/cdrom.h"
PATCH = Path(__file__).resolve().parents[1] / "patches/pcsx-redux/stage536-zero-inactive-cdrom-queue-element.patch"


def run(command, *, cwd=None):
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def validate(repository):
    repository = Path(repository).resolve()
    if not repository.is_dir():
        raise ValueError("pinned PCSX-Redux checkout is missing")
    head = run(["git", "-C", str(repository), "rev-parse", "HEAD"])
    if head != PINNED_COMMIT:
        raise ValueError("refusing non-pinned PCSX-Redux checkout")
    header = repository / HEADER
    if not header.is_file() or header.is_symlink():
        raise ValueError("pinned CD-ROM header is missing or is a symlink")
    blob = run(["git", "-C", str(repository), "hash-object", HEADER])
    if blob != PINNED_HEADER_BLOB:
        raise ValueError("pinned CD-ROM header blob changed")
    status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain", "--", HEADER],
        check=True, text=True, capture_output=True,
    ).stdout
    if status.strip():
        raise ValueError("refusing already-modified pinned CD-ROM header")

    original = header.read_text(encoding="utf-8")
    if original.count("        uint8_t payload[16];\n        uint8_t value;") != 1:
        raise ValueError("expected uninitialized QueueElement members are absent or duplicated")
    if original.count("        void clear() {\n            hasValue = false;\n            valueRead = false;\n            payloadSize = 0;\n            payloadIndex = 0;\n        }") != 1:
        raise ValueError("expected pinned QueueElement::clear body is absent or duplicated")

    with tempfile.TemporaryDirectory(prefix="stage536-patch-check-") as temporary:
        root = Path(temporary)
        target = root / HEADER
        target.parent.mkdir(parents=True)
        shutil.copyfile(header, target)
        run(["git", "apply", "--check", "--unsafe-paths", str(PATCH)], cwd=root)
        run(["git", "apply", "--unsafe-paths", str(PATCH)], cwd=root)
        patched = target.read_text(encoding="utf-8")
        expected = original.replace(
            "        uint8_t payload[16];\n        uint8_t value;",
            "        // The complete payload is serialized in savestates, including inactive bytes.\n"
            "        uint8_t payload[16] = {};\n"
            "        uint8_t value = 0;",
            1,
        ).replace(
            "        void clear() {\n"
            "            hasValue = false;\n"
            "            valueRead = false;\n"
            "            payloadSize = 0;\n"
            "            payloadIndex = 0;\n"
            "        }",
            "        void clear() {\n"
            "            // Keep the entire serialized queue element deterministic, not only its active prefix.\n"
            "            for (auto &byte : payload) byte = 0;\n"
            "            value = 0;\n"
            "            hasValue = false;\n"
            "            valueRead = false;\n"
            "            hitMax = false;\n"
            "            payloadSize = 0;\n"
            "            payloadIndex = 0;\n"
            "        }",
            1,
        )
        if patched != expected:
            raise ValueError("candidate patch changes unexpected upstream header content")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcsx_redux_checkout")
    args = parser.parse_args()
    try:
        validate(args.pcsx_redux_checkout)
    except (ValueError, OSError, subprocess.CalledProcessError):
        parser.exit(2, "STAGE536_UPSTREAM_PATCH_VALIDATION_FAILED\n")
    print("STAGE536_PATCH_APPLIES_TO_EXACT_PINNED_UPSTREAM_HEADER; NO_BUILD_OR_RUNTIME_ATTESTATION")


if __name__ == "__main__":
    main()
