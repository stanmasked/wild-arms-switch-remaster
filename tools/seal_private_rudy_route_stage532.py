#!/usr/bin/env python3
"""Stage532 owner-private Rudy -> Surf Village route integrity seal.

File integrity and self-consistent input declarations do NOT attest that
PCSX-Redux ran, Rudy was selected, or the target scene is Surf Village.
Keep every evidence file and generated manifest in private Google Drive.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from decode_private_opaque_rgb_png import decode_private_opaque_rgb_png

ROLES = ("disc_bin", "disc_cue", "selection_state", "selection_png",
         "arrival_state", "arrival_png", "input_trace")
LIMITS = {"disc_bin": 1024**3, "disc_cue": 8192,
          "selection_state": 256*1024**2, "arrival_state": 256*1024**2,
          "selection_png": 8*1024**2, "arrival_png": 8*1024**2,
          "input_trace": 64*1024}
KIND = "WA1_PRIVATE_RUDY_ROUTE_INTEGRITY"
MANIFEST = "stage532-rudy-route.private.json"
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


def paths_for(root, names):
    root = root_dir(root)
    if type(names) is not dict or set(names) != set(ROLES):
        raise ValueError("all seven evidence roles required")
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
        identities.append((st.st_dev, st.st_ino))
    if len(set(identities)) != len(ROLES):
        raise ValueError("private evidence paths alias")
    if paths["disc_bin"].stat().st_size % 2352:
        raise ValueError("BIN not aligned to MODE2/2352 sectors")
    return paths


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


def validate_cue(path, bin_name):
    raw = path.read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("CUE must be ASCII") from exc
    # This bounded first-disc capture uses one BINARY FILE / MODE2 track.
    declarations = [line.strip() for line in lines if line.strip() and not line.lstrip().upper().startswith("REM ")]
    files = [line for line in declarations if re.match(r"(?i)^FILE\s+", line)]
    tracks = [line for line in declarations if re.match(r"(?i)^TRACK\s+", line)]
    index = [line for line in declarations if re.match(r"(?i)^INDEX\s+", line)]
    if len(files) != 1 or len(tracks) != 1 or len(index) < 1:
        raise ValueError("CUE requires one BIN and one MODE2 track")
    m = re.fullmatch(r'FILE\s+"([^"/\\]+)"\s+BINARY', files[0], flags=re.I)
    if not m or m.group(1) != bin_name:
        raise ValueError("CUE FILE must match actual BIN basename")
    if re.fullmatch(r"TRACK\s+01\s+MODE2/2352", tracks[0], flags=re.I) is None:
        raise ValueError("CUE must contain MODE2/2352 track 01")
    if not any(re.fullmatch(r"INDEX\s+01\s+\d\d:\d\d:\d\d", x, flags=re.I) for x in index):
        raise ValueError("CUE lacks playable INDEX 01")
    if any(re.match(r"(?i)^(FILE|TRACK|INDEX)\b", x) for x in declarations if x not in files+tracks+index):
        raise ValueError("unsupported CUE directive")


def validate_inputs(path):
    item = load_strict_json(path.read_bytes())
    if (type(item) is not dict or set(item) != {"schema", "origin", "events"} or
            item["schema"] != "wild-arms-rudy-route-input-v1" or
            item["origin"] != "operator_declared_not_attested" or
            type(item["events"]) is not list or not 3 <= len(item["events"]) <= 2048):
        raise ValueError("invalid input journal schema")
    previous = -1
    active = False
    for index, event in enumerate(item["events"]):
        if (type(event) is not dict or set(event) != {"frame", "buttons"} or
                type(event["frame"]) is not int or not 0 <= event["frame"] <= 10_000_000 or
                event["frame"] <= previous or type(event["buttons"]) is not list or
                len(event["buttons"]) > len(BUTTONS) or
                any(type(x) is not str or x not in BUTTONS for x in event["buttons"]) or
                len(set(event["buttons"])) != len(event["buttons"])):
            raise ValueError("invalid ordered physical-button events")
        if index == 0 and (event["frame"] != 0 or event["buttons"]):
            raise ValueError("input journal must start at neutral frame zero")
        active |= bool(event["buttons"])
        previous = event["frame"]
    if not active or item["events"][-1]["buttons"]:
        raise ValueError("input journal must have actuation followed by neutral")
    return {"event_count": len(item["events"]), "last_declared_frame": previous}


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(paths):
    validate_cue(paths["disc_cue"], paths["disc_bin"].name)
    journal = validate_inputs(paths["input_trace"])
    (a_dim, a_rgb) = decode_private_opaque_rgb_png(paths["selection_png"].read_bytes())
    (b_dim, b_rgb) = decode_private_opaque_rgb_png(paths["arrival_png"].read_bytes())
    if a_dim != b_dim or a_rgb == b_rgb:
        raise ValueError("two independent same-size PNG rasters must differ")
    if hmac.compare_digest(sha_file(paths["selection_state"]), sha_file(paths["arrival_state"])):
        raise ValueError("pre/post emulator states must not be identical")
    return {"dimensions": list(a_dim), "different_screen_pixels": True, **journal}


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


def seal(root, names, manifest_name=MANIFEST):
    root = root_dir(root)
    target = root / basename(manifest_name)
    if target.exists() or target.is_symlink() or manifest_name in names.values():
        raise FileExistsError("private manifest already exists or aliases input")
    paths = paths_for(root, names)
    summary = audit(paths)
    records = file_records(paths)
    assert_original_bytes(paths, records)
    record = {"kind": KIND, "schema": 1, "private_only": True,
              "origin": "operator_claim_not_attested",
              "status": "INTEGRITY_ONLY_NO_GAMEPLAY_ATTESTATION",
              "files": records, "summary": summary}
    payload = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > 16384:
        raise ValueError("manifest too large")
    tmp = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".stage532-", suffix=".tmp", delete=False) as output:
            tmp = Path(output.name)
            os.chmod(tmp, 0o600)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        assert_original_bytes(paths, records)
        os.link(tmp, target)
        published = True
        assert_original_bytes(paths, records)
    except BaseException:
        if published:
            target.unlink(missing_ok=True)
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return record


def verify(root, manifest_name=MANIFEST):
    root = root_dir(root)
    target = root / basename(manifest_name)
    st = target.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not 0 < st.st_size <= 16384:
        raise ValueError("invalid private route manifest")
    record = load_strict_json(target.read_bytes())
    if (type(record) is not dict or set(record) != {
            "kind", "schema", "private_only", "origin", "status", "files", "summary"} or
            record["kind"] != KIND or type(record["schema"]) is not int or record["schema"] != 1 or
            record["private_only"] is not True or record["origin"] != "operator_claim_not_attested" or
            record["status"] != "INTEGRITY_ONLY_NO_GAMEPLAY_ATTESTATION"):
        raise ValueError("unexpected manifest/provenance claim")
    files = record["files"]
    if type(files) is not dict or set(files) != set(ROLES):
        raise ValueError("unknown private roles")
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
    summary = audit(paths)
    if summary != record["summary"]:
        raise ValueError("private route summary differs")
    assert_original_bytes(paths, files)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "verify"))
    parser.add_argument("private_directory")
    parser.add_argument("--manifest-name", default=MANIFEST)
    for role in ROLES:
        parser.add_argument("--" + role.replace("_", "-"))
    a = parser.parse_args()
    try:
        if a.action == "seal":
            names = {role: getattr(a, role) for role in ROLES}
            if any(name is None for name in names.values()):
                parser.error("seal requires seven explicit evidence-role filenames")
            seal(a.private_directory, names, a.manifest_name)
            print("PRIVATE_RUDY_ROUTE_INTEGRITY_SEALED; GAMEPLAY_NOT_ATTESTED")
        else:
            verify(a.private_directory, a.manifest_name)
            print("PRIVATE_RUDY_ROUTE_INTEGRITY_VERIFIED; GAMEPLAY_NOT_ATTESTED")
    except (ValueError, OSError, json.JSONDecodeError):
        # Suppress private paths, SHA-256 values and original filenames from stdout/stderr.
        parser.exit(2, "INVALID_PRIVATE_RUDY_ROUTE_EVIDENCE\n")


if __name__ == "__main__":
    main()
