#!/usr/bin/env python3
"""Stage430: privately capture only a stable, API-reported paused PS1 VRAM.

READ-ONLY: three local execution-flow GETs and two local GPU VRAM GETs.
No pause/resume POSTs, no external network, no original assets in CI.
A stable byte sequence still does not authenticate Surf Village, frame
number, actual GPU packet timing, or CLUT use.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener

from capture_private_pcsx_redux_vram import (
    DEFAULT_URL, MANIFEST_KIND, RAW_VRAM_BYTES, _NeverRedirect,
    _publish_without_overwrite, _validate_basename,
    download_private_vram, validate_endpoint, verify_private_vram,
)

FLOW_PATH = "/api/v1/execution-flow"
MAX_FLOW_RESPONSE = 8192


def _strict_json_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("execution-flow returned duplicate JSON field")
        obj[key] = value
    return obj


def read_private_pause_state(vram_url=DEFAULT_URL, *, opener=None, timeout=10):
    """Observe PCSX-Redux running flag; never mutate emulator state."""
    validate_endpoint(vram_url)
    if type(timeout) not in (int, float) or isinstance(timeout, bool) or not 0 < timeout <= 120:
        raise ValueError("invalid timeout")
    parsed = urlsplit(vram_url)
    url = urlunsplit((parsed.scheme, parsed.netloc, FLOW_PATH, "", ""))
    if opener is None:
        opener = build_opener(ProxyHandler({}), _NeverRedirect())
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        if response.geturl() != url:
            raise ValueError("execution-flow redirected away from loopback")
        if response.status != 200:
            raise ValueError("execution-flow expected HTTP 200")
        payload = response.read(MAX_FLOW_RESPONSE + 1)
    if not payload or len(payload) > MAX_FLOW_RESPONSE:
        raise ValueError("execution-flow response empty or too large")
    try:
        document = json.loads(payload.decode("utf-8"),
                              object_pairs_hook=_strict_json_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed execution-flow JSON") from exc
    if not isinstance(document, dict) or type(document.get("running")) is not bool:
        raise ValueError("execution-flow JSON missing boolean running flag")
    return document["running"]


def capture_stable_private_vram(
        directory, *, basename="surf_village_stable",
        url=DEFAULT_URL, label="Surf Village (operator label only)",
        opener=None):
    """Require paused status around TWO byte-identical full VRAM reads."""
    _validate_basename(basename)
    validate_endpoint(url)
    if type(label) is not str or not 1 <= len(label) <= 160:
        raise ValueError("invalid scene label")
    output = Path(directory)
    if not output.is_dir():
        raise ValueError("private output directory must already exist")
    raw_name = basename + ".u16le.bin"
    meta_name = basename + ".capture.json"
    if (output / raw_name).exists() or (output / meta_name).exists():
        raise FileExistsError("private capture basename already exists")
    if opener is None:
        opener = build_opener(ProxyHandler({}), _NeverRedirect())

    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator is running before the first VRAM read")
    first = download_private_vram(url, opener=opener)
    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator ran between VRAM reads")
    second = download_private_vram(url, opener=opener)
    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator resumed after second VRAM read")
    if first != second:
        raise ValueError("unstable VRAM: two paused reads differ; no capture saved")

    digest = hashlib.sha256(first).hexdigest()
    manifest = {
        "schema": 1,
        "kind": MANIFEST_KIND,
        "source": "PCSX-Redux localhost GET /api/v1/gpu/vram/raw",
        "vram_filename": raw_name,
        "manifest_filename": meta_name,
        "bytes": RAW_VRAM_BYTES,
        "vram_sha256": digest,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "operator_scene_label": label,
        "snapshot_read_count": 2,
        "execution_flow_read_count": 3,
        "api_reported_running_false_in_all_three_observations": True,
        "two_read_bytes_identical": True,
        "emulator_was_paused_at_capture_unverified": True,
        "game_map_and_frame_number_unverified": True,
        "little_endian_word_order_assumed_not_independently_verified": True,
        "no_gp0_packet_trace_included": True,
        "not_evidence_of_runtime_clut_selection": True,
        "no_original_bytes_in_metadata": True,
    }
    _publish_without_overwrite(output, first, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_directory", type=Path)
    parser.add_argument("--basename", default="surf_village_stable")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--label", default="Surf Village (operator label only)")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        report = verify_private_vram(args.private_directory, basename=args.basename)
    else:
        report = capture_stable_private_vram(
            args.private_directory, basename=args.basename,
            url=args.url, label=args.label)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
