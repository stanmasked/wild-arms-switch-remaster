#!/usr/bin/env python3
"""Stage532 owner-private Surf Village controlled-movement integrity seal.

The canonical BIN/CUE are verified by reference, not copied into the evidence
bundle. File hashes and internally consistent declarations do NOT attest
screenshot origin, game identity, or gameplay correctness.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile

from decode_private_opaque_rgb_png import decode_private_opaque_rgb_png

ROLES = ("before_state", "before_vram", "before_png",
         "after_state", "after_vram", "after_png", "input_trace")
LIMITS = {"before_state": 256*1024**2, "after_state": 256*1024**2,
          "before_vram": 1024*1024, "after_vram": 1024*1024,
          "before_png": 8*1024**2, "after_png": 8*1024**2,
          "input_trace": 64*1024}
SOURCE_BIN_LIMIT = 1024**3
SOURCE_CUE_LIMIT = 8192
VRAM_BYTES = 1024*512*2
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
KIND = "WA1_PRIVATE_SURF_VILLAGE_CONTROL_PROBE"
MANIFEST = "stage532-surf-control.private.json"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.() -]{0,119}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
BUTTONS = frozenset(("cross", "circle", "triangle", "square", "start", "select",
                     "dpad_up", "dpad_down", "dpad_left", "dpad_right"))


def basename(value):
    if (type(value) is not str or not NAME.fullmatch(value) or value in (".", "..")):
        raise ValueError("private evidence name must be a safe basename")
    return value


def root_dir(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("private directory must be a real directory")
    return root


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def load_strict_json(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_source(path, limit, label):
    path = Path(path)
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= limit):
        raise ValueError("canonical source must be a bounded regular file")
    return path


def validate_cue(path, bin_name):
    raw = path.read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("CUE must be ASCII") from exc
    declarations = [line.strip() for line in lines
                    if line.strip() and not line.lstrip().upper().startswith("REM ")]
    files = [line for line in declarations if re.match(r"(?i)^FILE\s+", line)]
    tracks = [line for line in declarations if re.match(r"(?i)^TRACK\s+", line)]
    indices = [line for line in declarations if re.match(r"(?i)^INDEX\s+", line)]
    if len(files) != 1 or len(tracks) != 1 or len(indices) < 1:
        raise ValueError("CUE requires one BIN and one MODE2 track")
    match = re.fullmatch(r'FILE\s+"([^"/\\]+)"\s+BINARY', files[0], flags=re.I)
    if not match or match.group(1) != bin_name:
        raise ValueError("CUE FILE must match the canonical BIN basename")
    if re.fullmatch(r"TRACK\s+01\s+MODE2/2352", tracks[0], flags=re.I) is None:
        raise ValueError("CUE must contain MODE2/2352 track 01")
    if not any(re.fullmatch(r"INDEX\s+01\s+\d\d:\d\d:\d\d", x, flags=re.I) for x in indices):
        raise ValueError("CUE lacks playable INDEX 01")
    if any(re.match(r"(?i)^(FILE|TRACK|INDEX)\b", x)
           for x in declarations if x not in files+tracks+indices):
        raise ValueError("unsupported CUE directive")


def source_record(disc_bin, disc_cue, bin_ref, cue_ref):
    bin_path = _regular_source(disc_bin, SOURCE_BIN_LIMIT, "BIN")
    cue_path = _regular_source(disc_cue, SOURCE_CUE_LIMIT, "CUE")
    if bin_path.parent.resolve() != cue_path.parent.resolve():
        raise ValueError("canonical BIN and CUE must be in the same directory")
    if bin_path.stat().st_size % 2352:
        raise ValueError("canonical BIN is not aligned to MODE2/2352 sectors")
    validate_cue(cue_path, bin_path.name)
    if (type(bin_ref) is not str or not bin_ref.startswith("https://") or
            type(cue_ref) is not str or not cue_ref.startswith("https://")):
        raise ValueError("canonical source Drive references required")
    return {
        "bin_name": bin_path.name, "bin_size": bin_path.stat().st_size,
        "bin_sha256": sha_file(bin_path), "cue_name": cue_path.name,
        "cue_size": cue_path.stat().st_size, "cue_sha256": sha_file(cue_path),
        "cue_file_reference": bin_path.name, "track_mode": "MODE2/2352",
        "source_refs": {"bin": bin_ref, "cue": cue_ref},
        "canonical_source_not_bundled": True,
    }


def paths_for(root, names):
    root = root_dir(root)
    if type(names) is not dict or set(names) != set(ROLES):
        raise ValueError("all seven controlled-movement evidence roles required")
    names = {role: basename(names[role]) for role in ROLES}
    if len(set(names.values())) != len(ROLES) or MANIFEST in names.values():
        raise ValueError("evidence roles must be distinct")
    paths = {role: root/name for role, name in names.items()}
    identities = []
    for role, path in paths.items():
        st = path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or
                not 0 < st.st_size <= LIMITS[role]):
            raise ValueError("private evidence must be bounded regular single-link files")
        if role.endswith("_vram") and st.st_size != VRAM_BYTES:
            raise ValueError("raw VRAM must be exactly 1 MiB")
        identities.append((st.st_dev, st.st_ino))
    if len(set(identities)) != len(ROLES):
        raise ValueError("private evidence paths alias")
    return paths


def validate_inputs(path):
    item = load_strict_json(path.read_bytes())
    if (type(item) is not dict or set(item) != {"schema", "origin", "events"} or
            item["schema"] != "wild-arms-surf-control-input-v1" or
            item["origin"] != "operator_declared_not_attested" or
            type(item["events"]) is not list or not 3 <= len(item["events"]) <= 2048):
        raise ValueError("invalid emulated controller input journal schema")
    previous = -1
    active = False
    for index, event in enumerate(item["events"]):
        if (type(event) is not dict or set(event) != {"frame", "buttons"} or
                type(event["frame"]) is not int or not 0 <= event["frame"] <= 10_000_000 or
                event["frame"] <= previous or type(event["buttons"]) is not list or
                len(event["buttons"]) > len(BUTTONS) or
                any(type(x) is not str or x not in BUTTONS for x in event["buttons"]) or
                len(set(event["buttons"])) != len(event["buttons"])):
            raise ValueError("invalid ordered emulated controller state events")
        if index == 0 and (event["frame"] != 0 or event["buttons"]):
            raise ValueError("input journal must start at neutral frame zero")
        active |= bool(event["buttons"])
        previous = event["frame"]
    if not active or item["events"][-1]["buttons"]:
        raise ValueError("input journal must contain actuation and end at neutral")
    return {"event_count": len(item["events"]), "last_declared_frame": previous,
            "input_source": "PCSX-Redux Lua pad override; operator-declared, not hardware-attested"}


def framebuffer_rgb_from_vram(raw):
    """Decode the original top-left 320x240 RGB555 framebuffer crop."""
    if type(raw) is not bytes or len(raw) != VRAM_BYTES:
        raise ValueError("raw VRAM must be exactly 1 MiB")
    output = bytearray(FRAME_WIDTH*FRAME_HEIGHT*3)
    dst = 0
    for y in range(FRAME_HEIGHT):
        row = y*1024*2
        for x in range(FRAME_WIDTH):
            offset = row+x*2
            value = raw[offset] | (raw[offset+1] << 8)
            output[dst] = ((value & 31)*255)//31
            output[dst+1] = (((value >> 5) & 31)*255)//31
            output[dst+2] = (((value >> 10) & 31)*255)//31
            dst += 3
    return bytes(output)


def audit(paths, source):
    journal = validate_inputs(paths["input_trace"])
    before_dim, before_rgb = decode_private_opaque_rgb_png(paths["before_png"].read_bytes())
    after_dim, after_rgb = decode_private_opaque_rgb_png(paths["after_png"].read_bytes())
    if before_dim != (FRAME_WIDTH, FRAME_HEIGHT) or after_dim != (FRAME_WIDTH, FRAME_HEIGHT):
        raise ValueError("framebuffer PNGs must be exact unscaled 320x240 images")
    before_vram = paths["before_vram"].read_bytes()
    after_vram = paths["after_vram"].read_bytes()
    if before_rgb != framebuffer_rgb_from_vram(before_vram):
        raise ValueError("before PNG does not match raw VRAM framebuffer crop")
    if after_rgb != framebuffer_rgb_from_vram(after_vram):
        raise ValueError("after PNG does not match raw VRAM framebuffer crop")
    if before_rgb == after_rgb or before_vram == after_vram:
        raise ValueError("before/after framebuffer evidence must differ")
    if hmac.compare_digest(sha_file(paths["before_state"]), sha_file(paths["after_state"])):
        raise ValueError("before/after emulator states must differ")
    return {"dimensions": [FRAME_WIDTH, FRAME_HEIGHT],
            "framebuffer_pngs_bound_to_raw_vram": True,
            "before_after_pixels_differ": True, "before_after_vram_differ": True,
            "before_after_state_bytes_differ": True, **journal}


def file_records(paths):
    return {role: {"name": path.name, "size": path.stat().st_size,
                   "sha256": sha_file(path)} for role, path in paths.items()}


def assert_original_bytes(paths, records):
    for role, path in paths.items():
        st = path.lstat()
        rec = records[role]
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or
                st.st_size != rec["size"] or
                not hmac.compare_digest(sha_file(path), rec["sha256"])):
            raise ValueError("private evidence bytes differ from manifest")


def assert_source_unchanged(disc_bin, disc_cue, expected):
    current = source_record(disc_bin, disc_cue,
                            expected["source_refs"]["bin"],
                            expected["source_refs"]["cue"])
    if current != expected:
        raise ValueError("canonical source BIN/CUE differs from private manifest")


def seal(root, names, *, disc_bin, disc_cue, bin_ref, cue_ref,
         manifest_name=MANIFEST):
    root = root_dir(root)
    manifest_name = basename(manifest_name)
    target = root/manifest_name
    if target.exists() or target.is_symlink() or (type(names) is dict and manifest_name in names.values()):
        raise FileExistsError("private manifest already exists or aliases input")
    source = source_record(disc_bin, disc_cue, bin_ref, cue_ref)
    paths = paths_for(root, names)
    summary = audit(paths, source)
    records = file_records(paths)
    assert_original_bytes(paths, records)
    assert_source_unchanged(disc_bin, disc_cue, source)
    record = {"kind": KIND, "schema": 2, "private_only": True,
              "origin": "operator_claim_not_attested",
              "status": "INTEGRITY_ONLY_NO_GAMEPLAY_ATTESTATION",
              "source_disc": source, "files": records, "summary": summary}
    payload = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > 32768:
        raise ValueError("private manifest too large")
    temp = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".stage532-", suffix=".tmp", delete=False) as output:
            temp = Path(output.name)
            os.chmod(temp, 0o600)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        assert_original_bytes(paths, records)
        assert_source_unchanged(disc_bin, disc_cue, source)
        os.link(temp, target)
        published = True
        assert_original_bytes(paths, records)
        assert_source_unchanged(disc_bin, disc_cue, source)
    except BaseException:
        if published:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return record


def verify(root, *, disc_bin, disc_cue, manifest_name=MANIFEST):
    root = root_dir(root)
    target = root/basename(manifest_name)
    st = target.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not 0 < st.st_size <= 32768:
        raise ValueError("invalid private controlled-movement manifest")
    record = load_strict_json(target.read_bytes())
    if (type(record) is not dict or set(record) != {
            "kind", "schema", "private_only", "origin", "status",
            "source_disc", "files", "summary"} or record["kind"] != KIND or
            type(record["schema"]) is not int or record["schema"] != 2 or
            record["private_only"] is not True or
            record["origin"] != "operator_claim_not_attested" or
            record["status"] != "INTEGRITY_ONLY_NO_GAMEPLAY_ATTESTATION"):
        raise ValueError("unexpected private manifest/provenance claim")
    source = record["source_disc"]
    if (type(source) is not dict or set(source) != {
            "bin_name", "bin_size", "bin_sha256", "cue_name", "cue_size",
            "cue_sha256", "cue_file_reference", "track_mode", "source_refs",
            "canonical_source_not_bundled"} or
            type(source["bin_name"]) is not str or type(source["cue_name"]) is not str or
            type(source["bin_size"]) is not int or source["bin_size"] <= 0 or
            type(source["cue_size"]) is not int or source["cue_size"] <= 0 or
            type(source["bin_sha256"]) is not str or not SHA256.fullmatch(source["bin_sha256"]) or
            type(source["cue_sha256"]) is not str or not SHA256.fullmatch(source["cue_sha256"]) or
            source["cue_file_reference"] != source["bin_name"] or
            source["track_mode"] != "MODE2/2352" or source["canonical_source_not_bundled"] is not True or
            type(source["source_refs"]) is not dict or set(source["source_refs"]) != {"bin", "cue"}):
        raise ValueError("malformed canonical source reference")
    if source_record(disc_bin, disc_cue, source["source_refs"]["bin"],
                     source["source_refs"]["cue"]) != source:
        raise ValueError("canonical source BIN/CUE differs from private manifest")
    files = record["files"]
    if type(files) is not dict or set(files) != set(ROLES):
        raise ValueError("unknown private evidence roles")
    names = {}
    for role in ROLES:
        item = files[role]
        if (type(item) is not dict or set(item) != {"name", "size", "sha256"} or
                type(item["size"]) is not int or not 0 < item["size"] <= LIMITS[role] or
                type(item["sha256"]) is not str or not SHA256.fullmatch(item["sha256"])):
            raise ValueError("malformed private evidence metadata")
        names[role] = basename(item["name"])
    if manifest_name in names.values():
        raise ValueError("manifest aliases evidence")
    paths = paths_for(root, names)
    assert_original_bytes(paths, files)
    summary = audit(paths, source)
    if summary != record["summary"]:
        raise ValueError("private controlled-movement summary differs")
    assert_original_bytes(paths, files)
    assert_source_unchanged(disc_bin, disc_cue, source)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "verify"))
    parser.add_argument("private_directory")
    parser.add_argument("--manifest-name", default=MANIFEST)
    parser.add_argument("--disc-bin")
    parser.add_argument("--disc-cue")
    parser.add_argument("--bin-ref")
    parser.add_argument("--cue-ref")
    for role in ROLES:
        parser.add_argument("--"+role.replace("_", "-"))
    args = parser.parse_args()
    try:
        if not args.disc_bin or not args.disc_cue:
            parser.error("seal and verify require external canonical --disc-bin and --disc-cue")
        if args.action == "seal":
            names = {role: getattr(args, role) for role in ROLES}
            if any(name is None for name in names.values()):
                parser.error("seal requires all seven private evidence-role filenames")
            if not args.bin_ref or not args.cue_ref:
                parser.error("seal requires canonical Drive --bin-ref and --cue-ref")
            seal(args.private_directory, names, disc_bin=args.disc_bin,
                 disc_cue=args.disc_cue, bin_ref=args.bin_ref, cue_ref=args.cue_ref,
                 manifest_name=args.manifest_name)
            print("PRIVATE_SURF_CONTROL_INTEGRITY_SEALED; GAMEPLAY_NOT_ATTESTED")
        else:
            verify(args.private_directory, disc_bin=args.disc_bin,
                   disc_cue=args.disc_cue, manifest_name=args.manifest_name)
            print("PRIVATE_SURF_CONTROL_INTEGRITY_VERIFIED; GAMEPLAY_NOT_ATTESTED")
    except (ValueError, OSError, json.JSONDecodeError):
        parser.exit(2, "INVALID_PRIVATE_SURF_CONTROL_EVIDENCE\n")


if __name__ == "__main__":
    main()
