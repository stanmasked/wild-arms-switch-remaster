#!/usr/bin/env python3
"""Owner-private, localhost-only PCSX-Redux PS1 VRAM snapshot capture.

Consumes raw 1024x512x16-bit VRAM from PCSX-Redux's documented local REST
endpoint. Never uploads bytes or contacts external hosts. A VRAM snapshot
does NOT authenticate map identity, frame number, GP0 chronology, byte order,
or a GPU CLUT selection. All produced files must stay off public GitHub.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import (HTTPRedirectHandler, ProxyHandler, Request,
                            build_opener)

RAW_VRAM_BYTES = 1024 * 512 * 2
DEFAULT_URL = "http://127.0.0.1:8080/api/v1/gpu/vram/raw"
MANIFEST_KIND = "WA1_PRIVATE_PCSX_REDUX_RAW_VRAM_CAPTURE"
BASENAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)


class _NeverRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("HTTP redirect blocked: capture must remain loopback-only")


def validate_endpoint(url):
    if type(url) is not str:
        raise ValueError("endpoint must be a string")
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError as exc:
        raise ValueError("invalid loopback endpoint") from exc
    if (u.scheme != "http" or u.hostname not in ("127.0.0.1", "::1")
            or u.username is not None or u.password is not None
            or port == 0
            or u.path != "/api/v1/gpu/vram/raw" or u.query or u.fragment):
        raise ValueError("only exact PCSX-Redux loopback VRAM GET endpoint is allowed")
    return url


def _validate_basename(name):
    if type(name) is not str or BASENAME_RE.fullmatch(name) is None:
        raise ValueError("basename must be 1..64 safe ASCII characters")
    return name


def download_private_vram(url=DEFAULT_URL, *, opener=None, timeout=10):
    """Return full raw VRAM, enforcing redirects/size/host invariants.

    A caller may inject a synthetic response opener for offline tests.
    """
    validate_endpoint(url)
    if type(timeout) not in (int, float) or isinstance(timeout, bool) or not 0 < timeout <= 120:
        raise ValueError("timeout outside (0,120]")
    if opener is None:
        opener = build_opener(ProxyHandler({}), _NeverRedirect())
    request = Request(url, method="GET", headers={"Accept": "application/octet-stream"})
    with opener.open(request, timeout=timeout) as response:
        if response.geturl() != url:
            raise ValueError("response redirected away from requested loopback URL")
        if response.status != 200:
            raise ValueError("expected HTTP 200 raw VRAM response")
        data = response.read(RAW_VRAM_BYTES + 1)
        if len(data) != RAW_VRAM_BYTES:
            raise ValueError("raw VRAM must be exactly 1048576 bytes")
        return data


def _temporary_private_file(directory, data):
    fd, name = tempfile.mkstemp(prefix=".stage429-private-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        return Path(name)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def _publish_without_overwrite(output, raw, manifest):
    """Publish two files via no-clobber hard links, roll back on failure."""
    if not output.is_dir():
        raise ValueError("private output directory must already exist")
    binary = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    target_raw = output / manifest["vram_filename"]
    target_meta = output / manifest["manifest_filename"]
    if target_raw.exists() or target_meta.exists():
        raise FileExistsError("snapshot basename already exists")
    temps = []
    published = []
    try:
        temps.append(_temporary_private_file(output, raw))
        temps.append(_temporary_private_file(output, binary))
        os.link(temps[0], target_raw)  # EEXIST is fatal: never replace.
        published.append(target_raw)
        os.link(temps[1], target_meta)
        published.append(target_meta)
    except BaseException:
        for path in reversed(published):
            path.unlink()
        raise
    finally:
        for temp in temps:
            temp.unlink(missing_ok=True)


def capture_private_vram(output_directory, *, basename="surf_village_vram",
                         url=DEFAULT_URL, label="Surf Village (operator label only)",
                         opener=None):
    _validate_basename(basename)
    validate_endpoint(url)
    if type(label) is not str or not 1 <= len(label) <= 160:
        raise ValueError("label must be a non-empty string up to 160 chars")
    folder = Path(output_directory)
    if not folder.is_dir():
        raise ValueError("private output directory must already exist")
    raw_name = basename + ".u16le.bin"
    meta_name = basename + ".capture.json"
    if (folder / raw_name).exists() or (folder / meta_name).exists():
        raise FileExistsError("snapshot basename already exists")
    raw = download_private_vram(url, opener=opener)
    manifest = {
        "schema": 1,
        "kind": MANIFEST_KIND,
        "source": "PCSX-Redux localhost GET /api/v1/gpu/vram/raw",
        "vram_filename": raw_name,
        "manifest_filename": meta_name,
        "bytes": len(raw),
        "vram_sha256": hashlib.sha256(raw).hexdigest(),
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "operator_scene_label": label,
        "emulator_was_paused_at_capture_unverified": True,
        "game_map_and_frame_number_unverified": True,
        "little_endian_word_order_assumed_not_independently_verified": True,
        "no_gp0_packet_trace_included": True,
        "not_evidence_of_runtime_clut_selection": True,
        "no_original_bytes_in_metadata": True,
    }
    _publish_without_overwrite(folder, raw, manifest)
    return manifest


def verify_private_vram(output_directory, *, basename="surf_village_vram"):
    _validate_basename(basename)
    folder = Path(output_directory)
    meta = folder / (basename + ".capture.json")
    document = json.loads(meta.read_text(encoding="utf-8"))
    if (not isinstance(document, dict) or
            document.get("schema") != 1 or document.get("kind") != MANIFEST_KIND or
            document.get("vram_filename") != basename + ".u16le.bin" or
            document.get("manifest_filename") != meta.name or
            document.get("bytes") != RAW_VRAM_BYTES or
            not isinstance(document.get("vram_sha256"), str) or
            re.fullmatch(r"[0-9a-f]{64}", document["vram_sha256"]) is None):
        raise ValueError("malformed private capture manifest")
    snapshot = folder / document["vram_filename"]
    if snapshot.stat().st_size != RAW_VRAM_BYTES:
        raise ValueError("VRAM snapshot size changed")
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != document["vram_sha256"]:
        raise ValueError("VRAM snapshot SHA-256 mismatch")
    return {"verified": True, "vram_sha256": document["vram_sha256"],
            "bytes": RAW_VRAM_BYTES,
            "capture_claims_game_frame_identity": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_directory", type=Path)
    parser.add_argument("--basename", default="surf_village_vram")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--label", default="Surf Village (operator label only)")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        result = verify_private_vram(args.private_directory, basename=args.basename)
    else:
        result = capture_private_vram(args.private_directory, basename=args.basename,
                                      url=args.url, label=args.label)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
