"""Stage 263F: read-only, fail-closed /proc inventory for known custody writers.

This tool observes all numerically identified PIDs in the current procfs
mount, and refuses a live process running a PINNED known writer path or
holding the enrolled custody DB/parent directory/SQLite sidecar inode.
It cannot inventory a process that has no file currently open and can
start later, another PID namespace, alternate databases or privileged
actors. NEVER a witness-fence retirement authorization.
"""
import argparse
from contextlib import closing
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = 'wild-arms-ps1-known-custody-writer-binaries-v1'
REPORT_SCHEMA = 'wild-arms-ps1-linux-writer-inventory-report-v1'
DOMAIN = b'wild-arms-ps1-linux-writer-inventory-v1\x00'
MAX_MANIFEST = 8192
MAX_WRITERS = 32
MAX_PIDS = 32768
MAX_FDS = 65536
MAX_PROC_STAT = 8192
MAX_READLINK = 4096
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_PID = re.compile(r'[1-9][0-9]{0,9}\Z')


class InventoryConflict(ValueError):
    """Process scan incomplete, evidence changed, or a writer is live."""


def _canonical(item):
    return (json.dumps(item, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True) + '\n').encode('ascii')


def _strict_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicated inventory JSON key')
            result[k] = v
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def _abs_path(value):
    if (type(value) is not str or not value.startswith('/')
            or len(value) > 1024 or '\x00' in value
            or value == '/' or value.endswith('/')
            or any(x in ('.', '..', '') for x in value.split('/')[1:])):
        raise ValueError('invalid enrolled absolute writer path')
    return value


def _manifest(raw, trusted_sha256):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_MANIFEST:
        raise ValueError('bounded independent writer inventory required')
    if type(trusted_sha256) is not str or not _SHA256.fullmatch(trusted_sha256):
        raise ValueError('invalid independently pinned inventory SHA-256')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), trusted_sha256):
        raise InventoryConflict('writer manifest does not match external pin')
    body = _strict_json(raw)
    if (type(body) is not dict or set(body) != {'schema', 'executables'}
            or body['schema'] != SCHEMA
            or type(body['executables']) is not list
            or not 0 < len(body['executables']) <= MAX_WRITERS
            or raw != _canonical(body)):
        raise ValueError('invalid canonical enrolled binary manifest')
    previous = ''
    paths = []
    for entry in body['executables']:
        if (type(entry) is not dict or set(entry) != {'path','sha256'}
                or type(entry['sha256']) is not str
                or not _SHA256.fullmatch(entry['sha256'])):
            raise ValueError('invalid exact binary catalogue entry')
        path = _abs_path(entry['path'])
        if path <= previous:
            raise ValueError('executable inventory must be sorted and unique')
        previous = path
        paths.append(path)
    return tuple(paths)


def _read_at(fd, name, limit):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        data = os.read(handle, limit + 1)
        if len(data) > limit:
            raise InventoryConflict('oversized procfs status')
        return data
    finally:
        os.close(handle)


def _process_identity(pidfd, pid):
    raw = _read_at(pidfd, 'stat', MAX_PROC_STAT)
    close = raw.rfind(b') ')
    if close < 0 or not raw.startswith((str(pid)+' (').encode()):
        raise InventoryConflict('malformed /proc process identity')
    rest = raw[close+2:].split()
    # /proc/<pid>/stat: field 22 starttime. Fields after (comm) begin at 3.
    if len(rest) < 20 or not rest[19].isdigit():
        raise InventoryConflict('missing Linux process starttime')
    return int(rest[19])


def _target_inodes(db_path, db_dev, db_ino):
    path = Path(_abs_path(str(db_path)))
    if (type(db_dev) is not int or db_dev < 0
            or type(db_ino) is not int or db_ino <= 0):
        raise ValueError('invalid enrolled custody DB dev/inode')
    db = path.stat()
    if not stat.S_ISREG(db.st_mode) or (db.st_dev, db.st_ino) != (db_dev, db_ino):
        raise InventoryConflict('custody DB changed since enrollment')
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode):
        raise InventoryConflict('custody directory identity invalid')
    targets = {(db.st_dev, db.st_ino), (parent.st_dev, parent.st_ino)}
    for ext in ('-wal','-shm','-journal'):
        side = Path(str(path)+ext)
        try:
            f = side.stat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(f.st_mode):
            raise InventoryConflict('unexpected SQLite auxiliary object')
        targets.add((f.st_dev, f.st_ino))
    return targets


def _mount_is_procfs():
    with open('/proc/self/mountinfo', encoding='utf-8') as inp:
        for line in inp:
            left, delim, right = line.partition(' - ')
            if not delim:
                continue
            fields = left.split()
            rfields = right.split()
            if len(fields) >= 5 and fields[4] == '/proc':
                return bool(rfields and rfields[0] == 'proc')
    return False


def _read_executable(pidfd):
    try:
        dest = os.readlink('exe', dir_fd=pidfd)
    except FileNotFoundError:
        # Kernel threads may have neither an executable nor open descriptors.
        return None
    if len(dest) > MAX_READLINK:
        raise InventoryConflict('oversized process executable path')
    return dest.removesuffix(' (deleted)')


def _scan(proc_root, enrolled_paths, targets):
    rootfd = os.open(proc_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with os.scandir(rootfd) as entries:
            pids = sorted(int(e.name) for e in entries
                          if _PID.fullmatch(e.name))
        if len(pids) > MAX_PIDS:
            raise InventoryConflict('process count exceeds bounded scan')
        survivors = []
        inspected = 0
        scanned_fds = 0
        for pid in pids:
            pidfd = os.open(str(pid), os.O_RDONLY | os.O_DIRECTORY |
                            os.O_NOFOLLOW, dir_fd=rootfd)
            try:
                start = _process_identity(pidfd, pid)
                exe = _read_executable(pidfd)
                known = exe in enrolled_paths
                fdroot = os.open('fd', os.O_RDONLY | os.O_DIRECTORY |
                                 os.O_NOFOLLOW, dir_fd=pidfd)
                try:
                    with os.scandir(fdroot) as entries:
                        fds = sorted(e.name for e in entries if e.name.isdigit())
                    scanned_fds += len(fds)
                    if scanned_fds > MAX_FDS:
                        raise InventoryConflict('file descriptor scan exceeds bound')
                    matches = []
                    for name in fds:
                        desc = os.stat(name, dir_fd=fdroot, follow_symlinks=True)
                        if (desc.st_dev, desc.st_ino) in targets:
                            matches.append(name)
                finally:
                    os.close(fdroot)
                # Detect PID reuse while inspecting each task.
                if _process_identity(pidfd, pid) != start:
                    raise InventoryConflict('PID reused while inspecting descriptors')
                inspected += 1
                if known or matches:
                    survivors.append((pid, start, bool(known), len(matches)))
            finally:
                os.close(pidfd)
        return inspected, scanned_fds, survivors
    except (FileNotFoundError, ProcessLookupError, PermissionError,
            NotADirectoryError) as exc:
        raise InventoryConflict('unreadable or disappearing process: scan incomplete') from exc
    finally:
        os.close(rootfd)


def inventory(manifest_raw, manifest_pin, db_path, db_dev, db_ino, *,
              proc_root=Path('/proc')):
    """Double-sample process/descriptor inventory; never authorize recovery."""
    paths = _manifest(manifest_raw, manifest_pin)
    first_targets = _target_inodes(db_path, db_dev, db_ino)
    first = _scan(proc_root, paths, first_targets)
    second_targets = _target_inodes(db_path, db_dev, db_ino)
    if first_targets != second_targets:
        raise InventoryConflict('SQLite filesystem objects changed during scan')
    second = _scan(proc_root, paths, second_targets)
    if first[2] or second[2]:
        raise InventoryConflict('live known custody executable or DB descriptor')
    # Other processes may come and go, but any truncated /proc scan fails.
    evidence = {
        'schema': REPORT_SCHEMA,
        'known_binary_count': len(paths),
        'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
        'custody_device': db_dev,
        'custody_inode': db_ino,
        'first_processes_inspected': first[0],
        'second_processes_inspected': second[0],
        'first_fds_inspected': first[1],
        'second_fds_inspected': second[1],
    }
    return {
        'schema': REPORT_SCHEMA,
        'observation_sha256': hashlib.sha256(DOMAIN + _canonical(evidence)).hexdigest(),
        'known_writer_executables_observed_running': False,
        'enrolled_sqlite_objects_observed_open': False,
        'bounded_procfs_scan_completed_twice': True,
        'all_possible_writer_processes_excluded': False,
        'alternate_namespaces_or_database_copies_excluded': False,
        'continuous_writer_revocation_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_binary_manifest', type=Path)
    parser.add_argument('trusted_manifest_sha256')
    parser.add_argument('custody_database', type=Path)
    parser.add_argument('--db-device', type=int, required=True)
    parser.add_argument('--db-inode', type=int, required=True)
    args = parser.parse_args(argv)
    result = {'schema': REPORT_SCHEMA, 'witness_fence_retired': False,
              'witness_fence_retirement_authorized': False}
    try:
        if not _mount_is_procfs():
            raise InventoryConflict('kernel procfs mount not verified')
        path = args.private_binary_manifest
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError('manifest must be private regular file')
        with path.open('rb') as source:
            raw = source.read(MAX_MANIFEST + 1)
        result.update(inventory(raw, args.trusted_manifest_sha256,
                                args.custody_database, args.db_device,
                                args.db_inode))
        code = 0
    except InventoryConflict:
        result['process_inventory_incomplete_or_writer_detected'] = True
        code = 1
    except (OSError, ValueError, TypeError, UnicodeError,
            json.JSONDecodeError):
        result['valid_input'] = False
        code = 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
