#!/usr/bin/env python3
"""Check Stage536 QueueElement patch against the exact pinned PCSX-Redux source.

This validates the source mapping and applies the candidate to a temporary
copy of one public upstream header. It does not modify the fetched checkout,
build PCSX-Redux, or run game data.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

PINNED_COMMIT = "de4a33e9a69abec4f567ae33567537f867dc2bba"
SOURCE_BLOBS = {
    "src/core/cdrom.h": "e82969125b2dd330420a6d2793e53ddd403fbe43",
    "src/core/cdrom.cc": "06766089543f068fed47a06cd85e0446f23ad524",
    "src/core/sstate.h": "ab2cf948dfe910275b4ac519673b52cbdaefb4bf",
    "src/core/sstate.cc": "2044f21d6bcf32f5c99766f038a398944d7f3cfe",
}
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

    sources = {}
    for path, expected_blob in SOURCE_BLOBS.items():
        source_path = repository / path
        if not source_path.is_file() or source_path.is_symlink():
            raise ValueError("pinned source file is missing or is a symlink: " + path)
        actual_blob = run(["git", "-C", str(repository), "hash-object", path])
        if actual_blob != expected_blob:
            raise ValueError("pinned source blob changed: " + path)
        status = subprocess.run(
            ["git", "-C", str(repository), "status", "--porcelain", "--", path],
            check=True, text=True, capture_output=True,
        ).stdout
        if status.strip():
            raise ValueError("refusing already-modified pinned source: " + path)
        sources[path] = source_path.read_text(encoding="utf-8")

    header_text = sources[HEADER]
    if header_text.count("        uint8_t payload[16];\n        uint8_t value;") != 1:
        raise ValueError("expected uninitialized QueueElement members are absent or duplicated")
    if header_text.count("        void clear() {\n            hasValue = false;\n            valueRead = false;\n            payloadSize = 0;\n            payloadIndex = 0;\n        }") != 1:
        raise ValueError("expected pinned QueueElement::clear body is absent or duplicated")

    cdrom_text = sources["src/core/cdrom.cc"]
    if ("QueueElement ready;" not in cdrom_text or
            "ready.pushPayloadData(getStatus());" not in cdrom_text or
            "maybeTriggerIRQ(Cause::DataReady, ready);" not in cdrom_text):
        raise ValueError("pinned DataReady writer path differs from Stage535 source mapping")
    if 'Protobuf::FixedBytes<16>, TYPESTRING("payload")' not in sources["src/core/sstate.h"]:
        raise ValueError("pinned savestate schema no longer declares a 16-byte payload")
    if "CDQueuePayload{cd->m_responseFifo[0].payload}" not in sources["src/core/sstate.cc"]:
        raise ValueError("pinned savestate serializer no longer maps responseFifo0 payload")

    with tempfile.TemporaryDirectory(prefix="stage536-patch-check-") as temporary:
        root = Path(temporary)
        target = root / HEADER
        target.parent.mkdir(parents=True)
        shutil.copyfile(repository / HEADER, target)
        run(["git", "apply", "--check", "--unsafe-paths", str(PATCH)], cwd=root)
        run(["git", "apply", "--unsafe-paths", str(PATCH)], cwd=root)
        patched = target.read_text(encoding="utf-8")
        expected = header_text.replace(
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
    print("STAGE536_PATCH_AND_STAGE535_SOURCE_MAPPING_MATCH_EXACT_PINNED_UPSTREAM; NO_BUILD_OR_RUNTIME_ATTESTATION")


if __name__ == "__main__":
    main()
