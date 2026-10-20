#!/usr/bin/env python3
"""Stage371: explicit OFFLINE, non-destructive WABJ recovery preparation.

Never writes, removes, renames or imports the two live damaged battle saves.
Restores only to a NEW quarantined directory when --execute is requested.
A user-supplied pinned SHA256 of each independent backup prevents accidental
selection of the wrong copy. CRC32 is for corruption, NOT authentication.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path

HEX_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
SLOT_FILE = "battle-progress.a"
MANIFEST_FILE = "recovery-manifest.json"


def _read_regular(path):
    # Open and validate the SAME inode. lstat()+Path.read_bytes() alone
    # can follow a symlink swapped in between those two operations.
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("sources must be regular files, not links/devices")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as file:
        opened = os.fstat(file.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or (before.st_dev, before.st_ino) !=
                   (opened.st_dev, opened.st_ino)):
            raise ValueError("source changed identity before safe read")
        if opened.st_size != 52:
            raise ValueError("WABJ source must be exactly 52 bytes")
        return file.read(53)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _journal_from_bytes(blob):
    # Mirror the WABJ/WABR v1 decoder in field_battle_file.hpp and
    # audit_nexium_battle_persistence.py; validate without writing a temp
    # file anywhere near the user's original save directory.
    import struct
    import zlib
    if len(blob) != 52 or blob[:4] != b"WABJ":
        raise ValueError("invalid WABJ size/magic")
    gen = struct.unpack_from("<Q", blob, 4)[0]
    body = blob[12:48]
    if (gen < 1 or body[:4] != b"WABR" or body[4] != 1
            or body[6:8] != b"\0\0" or body[28:32] != b"\0"*4):
        raise ValueError("invalid generation, WABR schema or reserved bytes")
    if zlib.crc32(body[:32]) != struct.unpack_from("<I", body, 32)[0]:
        raise ValueError("invalid WABR inner CRC")
    if zlib.crc32(blob[:48]) != struct.unpack_from("<I", blob, 48)[0]:
        raise ValueError("invalid WABJ outer CRC")
    outcome = body[5]
    wins, losses, retreats, exp, gella = struct.unpack_from("<IIIII", body, 8)
    if (outcome not in (0, 1, 2, 3) or
        (outcome == 0 and (wins or losses or retreats)) or
        (outcome == 1 and wins == 0) or
        (outcome == 2 and losses == 0) or
        (outcome == 3 and retreats == 0) or
        (wins == 0 and (exp or gella))):
        raise ValueError("invalid WABR history/reward semantics")
    return {
        "generation": gen, "outcome": outcome, "wins": wins,
        "losses": losses, "retreats": retreats,
        "experience": exp, "gella": gella, "sha256": _sha(blob),
    }


def _validated_backup(path, expected_sha):
    if not isinstance(expected_sha, str) or not HEX_SHA256.fullmatch(expected_sha):
        raise ValueError("trusted independent SHA-256 must be 64 hex characters")
    raw = _read_regular(path)
    actual = _sha(raw)
    if not hmac.compare_digest(actual, expected_sha.lower()):
        raise ValueError("backup does not match pinned SHA-256")
    record = _journal_from_bytes(raw)
    return raw, record


def _corrupt_snapshot(path):
    raw = _read_regular(path)
    if len(raw) != 52 or raw[:4] != b"WABJ":
        raise ValueError("damaged WABJ evidence must retain size/magic")
    try:
        _journal_from_bytes(raw)
    except ValueError:
        return raw
    raise ValueError("live save is still valid: offline double-corrupt recovery not required")


def _progress_is_monotonic(old, newer):
    return all(newer[field] >= old[field] for field in
               ("wins", "losses", "retreats", "experience", "gella"))


def prepare_recovery(damaged_a, damaged_b, backup_a, backup_b,
                     sha_a, sha_b, output_dir, execute=False):
    if (backup_a is None) != (sha_a is None) or (backup_b is None) != (sha_b is None):
        raise ValueError("each backup requires its own independently pinned SHA-256")
    if backup_a is None and backup_b is None:
        raise ValueError("at least one independent validated backup required")
    paths = [Path(x) for x in (damaged_a, damaged_b)]
    if backup_a is not None:
        paths.append(Path(backup_a))
    if backup_b is not None:
        paths.append(Path(backup_b))
    # Reject aliasing, including hard links. A recovery backup must not
    # be the same inode as either damaged live file.
    stats = [(p.lstat().st_dev, p.lstat().st_ino) for p in paths]
    if len(set(stats)) != len(stats):
        raise ValueError("live/copy inputs must be distinct physical files")
    damaged = [_corrupt_snapshot(path) for path in paths[:2]]
    backups = []
    if backup_a is not None:
        raw, record = _validated_backup(backup_a, sha_a)
        backups.append(("a", raw, record))
    if backup_b is not None:
        raw, record = _validated_backup(backup_b, sha_b)
        backups.append(("b", raw, record))
    ordered = sorted(backups, key=lambda value: value[2]["generation"])
    if len(ordered) == 2:
        low, high = ordered
        if low[2]["generation"] == high[2]["generation"]:
            if low[1] != high[1]:
                raise ValueError("equally generated backups conflict")
        elif not _progress_is_monotonic(low[2], high[2]):
            raise ValueError("newer backup regresses accumulated counters")
    slot, chosen_bytes, chosen = max(backups, key=lambda x:x[2]["generation"])
    out = Path(output_dir)
    if out.exists() or out.is_symlink():
        raise FileExistsError("recovery output already exists: refuse to overwrite")
    parent = out.parent
    if not parent.is_dir():
        raise FileNotFoundError("recovery parent directory does not exist")
    # Reject staging into any supplied source path or its enclosing directory.
    parent_real = parent.resolve(strict=True)
    # A recovery package must never be created inside the source game's
    # live battle save directory, including nested and symlinked parents.
    for damaged_path in paths[:2]:
        live_parent = damaged_path.parent.resolve(strict=True)
        if parent_real == live_parent or live_parent in parent_real.parents:
            raise ValueError("recovery output must be outside live save directories")
    if any(out.resolve(strict=False) == p.resolve(strict=True) for p in paths):
        raise ValueError("recovery output aliases a source file")
    # Publish via the canonical validated parent, not through the original
    # parent symlink which could be redirected while staging is prepared.
    out = parent_real / out.name
    if out.exists() or out.is_symlink():
        raise FileExistsError("canonical destination already exists")
    evidence = {
        "kind": "stage371_offline_verified_WABJ_staging",
        "backup_used": slot,
        "recovered": chosen,
        "verified_backup_sha256": _sha(chosen_bytes),
        "corrupt_a_sha256": _sha(damaged[0]),
        "corrupt_b_sha256": _sha(damaged[1]),
        "all_backups": {
            name: record for name, _, record in backups
        },
        "installed_to_live_sdmc": False,
        "requires_explicit_restore_by_owner": True,
        "restored_file": SLOT_FILE,
        "note": "CRC32 is NOT authentication; hashes must be obtained independently",
    }
    if not execute:
        return dict(evidence, mode="dry-run", staged=False)
    if out.name in ("", ".", ".."):
        raise ValueError("invalid recovery destination")
    stage = Path(tempfile.mkdtemp(prefix=".wild-arms-stage371-", dir=parent_real))
    try:
        os.chmod(stage, 0o700)
        def store(name, data):
            path = stage / name
            with path.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        store(SLOT_FILE, chosen_bytes)
        store(MANIFEST_FILE, (json.dumps(evidence, indent=2, sort_keys=True)
                              + "\n").encode("utf-8"))
        if _read_regular(stage / SLOT_FILE) != chosen_bytes:
            raise OSError("recovery read-back differs from trusted backup")
        if _journal_from_bytes(chosen_bytes) != chosen:
            raise OSError("recovered WABJ validation was not stable")
        if [_read_regular(p) for p in paths[:2]] != damaged:
            raise OSError("live corrupt sources changed while staging")
        for name, raw, _ in backups:
            path = backup_a if name == "a" else backup_b
            if _read_regular(path) != raw:
                raise OSError("trusted backup changed while staging")
        fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        # Atomically reserve a fresh directory. A check-then-rename alone
        # can replace somebody else's concurrently created EMPTY directory.
        # POSIX rename atomically exchanges our staged directory for our
        # own still-empty 0700 reservation, without touching user contents.
        if out.exists() or out.is_symlink():
            raise FileExistsError("destination appeared during staging")
        out.mkdir(mode=0o700)
        try:
            os.rename(stage, out)
            # Persist the newly published destination name, not just the
            # already-fsynced files and staging directory. If this fails,
            # report failure and leave the complete package in place for
            # offline inspection; never delete a possibly published save.
            parent_fd = os.open(parent_real, os.O_RDONLY |
                                getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except BaseException:
            # Never delete a directory which another process has populated.
            try:
                out.rmdir()
            except OSError:
                pass
            raise
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return dict(evidence, mode="explicit-staging", staged=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--damaged-a", type=Path, required=True)
    p.add_argument("--damaged-b", type=Path, required=True)
    p.add_argument("--backup-a", type=Path)
    p.add_argument("--backup-b", type=Path)
    p.add_argument("--sha256-a")
    p.add_argument("--sha256-b")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--execute", action="store_true",
                   help="explicitly stage a NEW directory, never touch live SDMC")
    options = p.parse_args()
    try:
        report = prepare_recovery(
            options.damaged_a, options.damaged_b, options.backup_a,
            options.backup_b, options.sha256_a, options.sha256_b,
            options.output_dir, execute=options.execute)
    except (ValueError, OSError, TypeError) as err:
        p.exit(2, f"Stage371 backup restore preparation rejected: {err}\n")
    print(json.dumps(report, sort_keys=True))
