#!/usr/bin/env python3
"""Prepare a NON-STANDARD diagnostic copy for NeXium's offset-16 NRO loader.

The original NRO is not changed. A padded copy is only used to isolate the
known off-by-16 bounds check; further boot correctness is NOT guaranteed.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_switch_nro import read_nro, NroFormatError

MAX_PAD = 16


def build_loader_probe(source, output, report):
    source, output, report = Path(source), Path(output), Path(report)
    if source.resolve() == output.resolve():
        raise ValueError("the original NRO must not be overwritten")
    if output.exists() or report.exists():
        raise ValueError("diagnostic outputs must not already exist")
    status = read_nro(source)
    if status["assets"] is not None or status["file_size"] != status["image_size"]:
        raise ValueError("only unadorned asset-free NROs can be diagnosed")
    data_segment = next(
        item for item in status["segments"] if item["name"] == "data")
    original = source.read_bytes()
    if original[0x10:0x14] != b"NRO0":
        raise ValueError("expected the standard 16-byte NroStart wrapper")
    # The pinned NeXium loader parses the header from input[16:], while
    # treating its data segment's offsets as if they started at input[0].
    # The published valid NRO's data section ends at the true file end,
    # so the emulator incorrectly considers it out of range by 16 bytes.
    data_end = data_segment["offset"] + data_segment["size"]
    if data_end != len(original):
        raise ValueError("data section must end at the original image end")
    required = 16 + data_end
    difference = required - len(original)
    if difference != MAX_PAD:
        raise ValueError("unexpected loader bound deficit")
    probe = original + bytes(difference)
    if probe[:len(original)] != original:
        raise AssertionError("diagnostic input was modified")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(probe)

    result = {
        "kind": "nexium_nonstandard_loader_bounds_probe",
        "standard_nro_unchanged": True,
        "probe_is_valid_standard_nro": False,
        "guest_execution_verified": False,
        "known_loader_header_skip_bytes": 16,
        "required_padding_bytes": difference,
        "original_file_size": len(original),
        "probe_file_size": len(probe),
        "original_nro_sha256": status["sha256"],
        "probe_sha256": hashlib.sha256(probe).hexdigest(),
        "diagnostic_goal": "isolate offset-16 NeXium segment-bounds error",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("probe", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build_loader_probe(args.source, args.probe, args.report)
    except (ValueError, OSError, NroFormatError) as exc:
        parser.exit(2, f"NeXium compatibility probe rejected: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
