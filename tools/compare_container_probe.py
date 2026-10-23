#!/usr/bin/env python3
"""Compare metadata-only prefix probe reports with a private header-probe catalog.

No input asset bytes are read here. Reports contain only file names, sizes,
sample hashes and metadata. Use prefix-mode output from probe_container.py.
"""
import argparse
import json
from pathlib import Path


def _canonical_name(value):
    name = str(value).replace("\\", "/").rsplit("/", 1)[-1]
    return name.split(";", 1)[0].upper()


def compare(reference_path, report_paths):
    with Path(reference_path).open("r", encoding="utf-8") as source:
        reference = json.load(source)
    if reference.get("kind") != "PRIVATE_DISC_HEADER_PROBE":
        raise ValueError("reference must be a PRIVATE_DISC_HEADER_PROBE report")
    expected_by_name = {}
    for item in reference.get("probed_files", []):
        name = _canonical_name(item.get("path", ""))
        if not name or name in expected_by_name:
            raise ValueError("reference contains an empty or duplicate canonical filename")
        expected_by_name[name] = item

    comparisons = []
    seen = set()
    for report_path in report_paths:
        with Path(report_path).open("r", encoding="utf-8") as source:
            actual = json.load(source)
        if actual.get("kind") != "BOUNDED_LOCAL_CONTAINER_PROBE":
            raise ValueError(f"{Path(report_path).name}: not a container probe report")
        name = _canonical_name(actual.get("input_name", ""))
        if not name or name in seen:
            raise ValueError("probe reports contain an empty or duplicate canonical filename")
        seen.add(name)
        expected = expected_by_name.get(name)
        if expected is None:
            comparisons.append({
                "file": name,
                "status": "MISMATCH",
                "reasons": ["NO_REFERENCE_ENTRY"],
            })
            continue

        reasons = []
        sample = actual.get("sample", {})
        if actual.get("file_size_bytes") != expected.get("file_size_bytes"):
            reasons.append("FILE_SIZE_MISMATCH")
        if sample.get("mode") != "prefix":
            reasons.append("SAMPLE_MODE_NOT_PREFIX")
        if sample.get("bytes_read") != expected.get("header_sample_length"):
            reasons.append("SAMPLE_LENGTH_MISMATCH")
        if sample.get("sha256") != expected.get("header_sample_sha256"):
            reasons.append("PREFIX_SHA256_MISMATCH")
        comparisons.append({
            "file": name,
            "status": "MISMATCH" if reasons else "MATCH",
            "reference_file_size_bytes": expected.get("file_size_bytes"),
            "observed_file_size_bytes": actual.get("file_size_bytes"),
            "reference_sample_length": expected.get("header_sample_length"),
            "observed_sample_length": sample.get("bytes_read"),
            "reasons": reasons,
        })

    if not comparisons:
        raise ValueError("at least one probe report is required")
    return {
        "schema": 1,
        "kind": "PRIVATE_HEADER_PROBE_COMPARISON",
        "overall": "PASS" if all(item["status"] == "MATCH" for item in comparisons) else "FAIL",
        "comparison_count": len(comparisons),
        "comparisons": comparisons,
        "payload_bytes_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="private header-probe JSON catalog")
    parser.add_argument("reports", nargs="+", type=Path, help="prefix-mode probe JSON report(s)")
    parser.add_argument("--output", type=Path, help="optional path for metadata-only comparison JSON")
    args = parser.parse_args()
    result = compare(args.reference, args.reports)
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    raise SystemExit(0 if result["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
