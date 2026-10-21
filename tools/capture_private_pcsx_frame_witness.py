#!/usr/bin/env python3
"""Owner-private PS1 witness: paused double VRAM + screenshot + disc info.

All input is fetched via exact PCSX-Redux loopback GET endpoints. The four
outputs stay on the owner's machine. Identical VRAM reads and paused-state
observations do NOT prove map identity or a GPU draw-time CLUT selection.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener
import zlib

from capture_private_pcsx_redux_vram import (
    DEFAULT_URL, MANIFEST_KIND, RAW_VRAM_BYTES, _NeverRedirect,
    _temporary_private_file, _validate_basename, download_private_vram,
    validate_endpoint, verify_private_vram,
)
from capture_private_stable_pcsx_vram import read_private_pause_state

SCREEN_PATH = "/api/v1/screen/still"
DISC_PATH = "/api/v1/cd/info"
MAX_SCREEN_BYTES = 16 * 1024 * 1024
MAX_DISC_INFO_BYTES = 32768
MAX_MANIFEST_BYTES = 32768
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _strict_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _same_loopback_endpoint(vram_url, suffix):
    validate_endpoint(vram_url)
    u = urlsplit(vram_url)
    return urlunsplit((u.scheme, u.netloc, suffix, "", ""))


def _read_exact_local_response(vram_url, path, limit, *, opener,
                               accept="application/octet-stream"):
    url = _same_loopback_endpoint(vram_url, path)
    request = Request(url, method="GET", headers={"Accept": accept})
    with opener.open(request, timeout=10) as reply:
        if reply.geturl() != url or reply.status != 200:
            raise ValueError("invalid or redirected local PCSX-Redux response")
        payload = reply.read(limit + 1)
    if not payload or len(payload) > limit:
        raise ValueError("local PCSX-Redux response empty or too large")
    return payload


def validate_private_png(source):
    """Validate complete bounded PNG chunk framing/CRC without decoding pixels."""
    if not isinstance(source, bytes) or not source.startswith(PNG_SIGNATURE):
        raise ValueError("screen/still response is not PNG")
    if len(source) > MAX_SCREEN_BYTES:
        raise ValueError("screen PNG too large")
    pos, width, height, have_idat, have_iend = 8, None, None, False, False
    while pos < len(source):
        if len(source) - pos < 12:
            raise ValueError("truncated PNG chunk")
        chunk_bytes = struct.unpack_from(">I", source, pos)[0]
        if chunk_bytes > MAX_SCREEN_BYTES or chunk_bytes > len(source) - pos - 12:
            raise ValueError("truncated or oversized PNG chunk")
        chunk_type = source[pos + 4:pos + 8]
        payload = source[pos + 8:pos + 8 + chunk_bytes]
        expected_crc = struct.unpack_from(">I", source, pos + 8 + chunk_bytes)[0]
        if zlib.crc32(chunk_type + payload) & 0xffffffff != expected_crc:
            raise ValueError("invalid PNG chunk CRC")
        if width is None:
            if chunk_type != b"IHDR" or chunk_bytes != 13:
                raise ValueError("PNG must begin with standard IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload)
            if (not 1 <= width <= 4096 or not 1 <= height <= 4096 or
                    depth not in (1, 2, 4, 8, 16) or color not in (0, 2, 3, 4, 6)
                    or compression != 0 or filtering != 0 or interlace not in (0, 1)):
                raise ValueError("unsupported PNG header")
        elif chunk_type == b"IHDR":
            raise ValueError("duplicate PNG header")
        if chunk_type == b"IDAT":
            have_idat = True
        if chunk_type == b"IEND":
            if chunk_bytes != 0 or not have_idat:
                raise ValueError("invalid PNG terminator")
            have_iend = True
            pos += chunk_bytes + 12
            if pos != len(source):
                raise ValueError("trailing bytes after PNG terminator")
            break
        pos += chunk_bytes + 12
    if not have_iend:
        raise ValueError("PNG terminator missing")
    return {"width": width, "height": height}


def read_private_disc_info(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_DISC_INFO_BYTES:
        raise ValueError("invalid disc info byte count")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid disc info JSON") from exc
    if not isinstance(doc, dict) or not doc:
        raise ValueError("expected nonempty CD information JSON object")
    return doc


def _publish_four_no_overwrite(directory, files):
    """All-or-cleanup linked publication; no existing file may be overwritten."""
    if not directory.is_dir():
        raise ValueError("private directory must already exist")
    for filename in files:
        if (directory / filename).exists() or (directory / filename).is_symlink():
            raise FileExistsError("private capture file already exists")
    staged = []
    linked = []
    try:
        for content in files.values():
            staged.append(_temporary_private_file(directory, content))
        for filename, source in zip(files, staged):
            destination = directory / filename
            os.link(source, destination)
            linked.append(destination)
    except BaseException:
        for published in reversed(linked):
            published.unlink()
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)


def capture_private_frame_witness(directory, *,
                                  basename="surf_village_frame_witness",
                                  url=DEFAULT_URL,
                                  label="Surf Village (operator label only)",
                                  opener=None):
    _validate_basename(basename)
    validate_endpoint(url)
    if type(label) is not str or not 1 <= len(label) <= 160:
        raise ValueError("invalid private scene label")
    folder = Path(directory)
    if not folder.is_dir():
        raise ValueError("private directory must already exist")
    raw_filename = basename + ".u16le.bin"
    screen_filename = basename + ".screen.png"
    cd_filename = basename + ".cdinfo.json"
    meta_filename = basename + ".capture.json"
    if any((folder / p).exists() or (folder / p).is_symlink() for p in
           (raw_filename, screen_filename, cd_filename, meta_filename)):
        raise FileExistsError("private capture basename already exists")
    if opener is None:
        opener = build_opener(ProxyHandler({}), _NeverRedirect())

    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator running before private witness")
    vram_first = download_private_vram(url, opener=opener)
    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator resumed before screenshot")
    screen = _read_exact_local_response(url, SCREEN_PATH, MAX_SCREEN_BYTES,
                                        opener=opener, accept="image/png")
    dimensions = validate_private_png(screen)
    cd_info = _read_exact_local_response(url, DISC_PATH, MAX_DISC_INFO_BYTES,
                                         opener=opener, accept="application/json")
    read_private_disc_info(cd_info)
    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator resumed before second VRAM read")
    vram_second = download_private_vram(url, opener=opener)
    if read_private_pause_state(url, opener=opener):
        raise ValueError("emulator running after private witness")
    if vram_first != vram_second:
        raise ValueError("VRAM changed during screenshot/CD witness; no files saved")

    manifest = {
        "schema": 1, "kind": MANIFEST_KIND,
        "source": "PCSX-Redux localhost GET /api/v1/gpu/vram/raw",
        "vram_filename": raw_filename, "manifest_filename": meta_filename,
        "bytes": RAW_VRAM_BYTES,
        "vram_sha256": hashlib.sha256(vram_first).hexdigest(),
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "operator_scene_label": label,
        "snapshot_read_count": 2, "execution_flow_read_count": 4,
        "api_reported_running_false_in_all_four_observations": True,
        "api_reported_running_false_in_all_three_observations": False,
        "two_read_bytes_identical": True,
        "screen_filename": screen_filename,
        "screen_sha256": hashlib.sha256(screen).hexdigest(),
        "screen_bytes": len(screen), "screen_dimensions": dimensions,
        "cd_info_filename": cd_filename,
        "cd_info_sha256": hashlib.sha256(cd_info).hexdigest(),
        "cd_info_bytes": len(cd_info),
        "emulator_was_paused_at_capture_unverified": True,
        "game_map_and_frame_number_unverified": True,
        "little_endian_word_order_assumed_not_independently_verified": True,
        "no_gp0_packet_trace_included": True,
        "not_evidence_of_runtime_clut_selection": True,
        "no_original_bytes_in_metadata": True,
    }
    _publish_four_no_overwrite(folder, {
        raw_filename: vram_first,
        screen_filename: screen,
        cd_filename: cd_info,
        meta_filename: (json.dumps(manifest, sort_keys=True,
                                    indent=2) + "\n").encode("utf-8"),
    })
    return manifest


def verify_private_frame_witness(directory, *,
                                 basename="surf_village_frame_witness"):
    _validate_basename(basename)
    root = Path(directory)
    meta_path = root / (basename + ".capture.json")
    if meta_path.is_symlink() or not 0 < meta_path.stat().st_size <= MAX_MANIFEST_BYTES:
        raise ValueError("invalid witness manifest")
    try:
        manifest = json.loads(meta_path.read_text(encoding="utf-8"),
                              object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid witness manifest JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("invalid witness manifest object")
    expected = {
        "schema": 1, "kind": MANIFEST_KIND,
        "vram_filename": basename + ".u16le.bin",
        "manifest_filename": basename + ".capture.json",
        "screen_filename": basename + ".screen.png",
        "cd_info_filename": basename + ".cdinfo.json",
        "bytes": RAW_VRAM_BYTES, "snapshot_read_count": 2,
        "execution_flow_read_count": 4,
        "api_reported_running_false_in_all_four_observations": True,
        "two_read_bytes_identical": True,
    }
    if any(type(manifest.get(k)) is not type(v) or manifest.get(k) != v
           for k, v in expected.items()):
        raise ValueError("invalid witness provenance fields")
    assets = (
        ("vram_filename", "vram_sha256", "bytes"),
        ("screen_filename", "screen_sha256", "screen_bytes"),
        ("cd_info_filename", "cd_info_sha256", "cd_info_bytes"),
    )
    contents = {}
    for name_field, hash_field, count_field in assets:
        path = root / manifest[name_field]
        digest = manifest.get(hash_field)
        count = manifest.get(count_field)
        if (path.is_symlink() or type(digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or type(count) is not int or not 0 < count <= MAX_SCREEN_BYTES
                or path.stat().st_size != count):
            raise ValueError("witness asset metadata or size mismatch")
        raw = path.read_bytes()
        if len(raw) != count or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("witness asset hash mismatch")
        contents[name_field] = raw
    dimensions = validate_private_png(contents["screen_filename"])
    if manifest.get("screen_dimensions") != dimensions:
        raise ValueError("screenshot dimensions mismatch")
    read_private_disc_info(contents["cd_info_filename"])
    return {"verified": True, "vram_sha256": manifest["vram_sha256"],
            "screen_sha256": manifest["screen_sha256"],
            "cd_info_sha256": manifest["cd_info_sha256"],
            "capture_claims_gpu_palette_mapping": False,
            "capture_claims_authenticated_scene_identity": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_directory", type=Path)
    ap.add_argument("--basename", default="surf_village_frame_witness")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--label", default="Surf Village (operator label only)")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()
    if args.verify_only:
        result = verify_private_frame_witness(args.private_directory,
                                              basename=args.basename)
    else:
        result = capture_private_frame_witness(
            args.private_directory, basename=args.basename,
            url=args.url, label=args.label)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
