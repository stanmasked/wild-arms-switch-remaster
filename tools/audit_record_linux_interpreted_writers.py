"""Stage 263G: read-only /proc audit of enrolled interpreted custody entrypoints.

A running enrolled Python interpreter is conservatively a POSSIBLE writer,
whether invoked with -m, a script, -c, or an unknown argument pattern.
Registered modules/scripts help identify provenance but never exempt another
invocation of that interpreter. Neither argv nor procfs is unforgeable.
No witness-fence retirement or host process mutation is implemented.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

try:
    from .audit_record_linux_writer_inventory import (
        _canonical, _strict_json, _abs_path, _SHA256, _PID,
        _read_executable, _read_at, _process_identity, _target_inodes,
        _mount_is_procfs, inventory as binary_inventory,
        InventoryConflict, MAX_PIDS, MAX_MANIFEST, MAX_WRITERS,
    )
except ImportError:
    from audit_record_linux_writer_inventory import (
        _canonical, _strict_json, _abs_path, _SHA256, _PID,
        _read_executable, _read_at, _process_identity, _target_inodes,
        _mount_is_procfs, inventory as binary_inventory,
        InventoryConflict, MAX_PIDS, MAX_MANIFEST, MAX_WRITERS,
    )

SCHEMA = 'wild-arms-ps1-known-interpreted-custody-entrypoints-v1'
REPORT_SCHEMA = 'wild-arms-ps1-linux-interpreted-writer-report-v1'
DOMAIN = b'wild-arms-ps1-linux-interpreted-writer-report-v1\x00'
MAX_ENTRYPOINT_MANIFEST = 16384
MAX_CMDLINE = 8192
MAX_ARGV = 96
_MODULE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z')


def _sorted_unique(items, *, validator, maximum):
    if (type(items) is not list or len(items) > maximum
            or any(type(x) is not str for x in items)):
        raise ValueError('invalid bounded interpreted entrypoint collection')
    verified = [validator(x) for x in items]
    if verified != sorted(set(verified)):
        raise ValueError('interpreted entrypoint catalogue not sorted and unique')
    return tuple(verified)


def _entrypoints(raw, independent_pin):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_ENTRYPOINT_MANIFEST
            or type(independent_pin) is not str
            or not _SHA256.fullmatch(independent_pin)):
        raise ValueError('invalid bounded interpreted entrypoint manifest')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), independent_pin):
        raise InventoryConflict('interpreted entrypoint manifest pin mismatch')
    body = _strict_json(raw)
    if (type(body) is not dict
            or set(body) != {'schema', 'interpreters', 'modules', 'scripts'}
            or body['schema'] != SCHEMA
            or raw != _canonical(body)):
        raise ValueError('noncanonical interpreted entrypoint manifest')
    interpreters = body['interpreters']
    if (type(interpreters) is not list
            or not 0 < len(interpreters) <= MAX_WRITERS):
        raise ValueError('no known interpreters enrolled')
    previous = ''
    paths = []
    for item in interpreters:
        if (type(item) is not dict or set(item) != {'path', 'sha256'}
                or type(item['sha256']) is not str
                or not _SHA256.fullmatch(item['sha256'])):
            raise ValueError('invalid Python interpreter enrollment')
        path = _abs_path(item['path'])
        if path <= previous:
            raise ValueError('interpreters must be sorted and unique')
        paths.append(path)
        previous = path
    modules = _sorted_unique(
        body['modules'],
        validator=lambda x: x if _MODULE.fullmatch(x) else
        (_ for _ in ()).throw(ValueError('invalid Python module name')),
        maximum=MAX_WRITERS)
    scripts = _sorted_unique(body['scripts'], validator=_abs_path,
                             maximum=MAX_WRITERS)
    if not modules and not scripts:
        raise ValueError('at least one interpreted custody entrypoint required')
    return tuple(paths), modules, scripts


def _bounded_argv(pidfd):
    raw = _read_at(pidfd, 'cmdline', MAX_CMDLINE)
    if not raw or not raw.endswith(b'\x00'):
        raise InventoryConflict('missing or truncated interpreter command line')
    args = raw[:-1].split(b'\x00')
    if not 1 <= len(args) <= MAX_ARGV or any(not x or len(x) > 1024
                                             for x in args):
        raise InventoryConflict('invalid or excessive interpreted arguments')
    try:
        return tuple(x.decode('utf-8', errors='strict') for x in args)
    except UnicodeError as exc:
        raise InventoryConflict('unreadable interpreted command line') from exc


def _classification(argv, modules, scripts):
    """Informative only: no cmdline classification permits a live interpreter."""
    for i, value in enumerate(argv[1:], 1):
        if value == '-m' and i + 1 < len(argv):
            return 'registered-module' if argv[i+1] in modules else 'unregistered-module'
        if value in scripts:
            return 'registered-script'
        if value in ('-c', '-'):
            return 'dynamic-python-code'
    return 'ambiguous-python-invocation'


def _interpreted_scan(proc_root, interpreters, modules, scripts):
    """Fail closed on vanished/unreadable PIDs even when they are not Python."""
    root = os.open(proc_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with os.scandir(root) as entries:
            pids = sorted(int(ent.name) for ent in entries
                          if _PID.fullmatch(ent.name))
        if len(pids) > MAX_PIDS:
            raise InventoryConflict('process inventory exceeds bound')
        matches = []
        for pid in pids:
            process = os.open(str(pid),
                              os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=root)
            try:
                identity = _process_identity(process, pid)
                exe = _read_executable(process)
                if exe in interpreters:
                    argv = _bounded_argv(process)
                    kind = _classification(argv, modules, scripts)
                    matches.append((pid, identity, kind))
                if _process_identity(process, pid) != identity:
                    raise InventoryConflict('PID reused during Python audit')
            finally:
                os.close(process)
        return len(pids), matches
    except (FileNotFoundError, ProcessLookupError, PermissionError,
            NotADirectoryError) as exc:
        raise InventoryConflict('partial or untrusted interpreted process scan') from exc
    finally:
        os.close(root)


def inspect(binary_raw, binary_pin, entrypoint_raw, entrypoint_pin,
            db_path, db_device, db_inode, *, proc_root=Path('/proc')):
    """Require BOTH the legacy binary/descriptor and the Python scan."""
    interpreter_paths, modules, scripts = _entrypoints(
        entrypoint_raw, entrypoint_pin)
    binary = binary_inventory(
        binary_raw, binary_pin, db_path, db_device, db_inode,
        proc_root=proc_root)
    before = _target_inodes(db_path, db_device, db_inode)
    first = _interpreted_scan(proc_root, interpreter_paths, modules, scripts)
    middle = _target_inodes(db_path, db_device, db_inode)
    second = _interpreted_scan(proc_root, interpreter_paths, modules, scripts)
    after = _target_inodes(db_path, db_device, db_inode)
    if before != middle or middle != after:
        raise InventoryConflict('custody SQLite inodes changed during Python scan')
    if first[1] or second[1]:
        raise InventoryConflict('known enrolled Python interpreter remains live')
    evidence = {
        'schema': REPORT_SCHEMA,
        'binary_inventory_sha256': binary['observation_sha256'],
        'entrypoint_manifest_sha256': hashlib.sha256(entrypoint_raw).hexdigest(),
        'interpreter_count': len(interpreter_paths),
        'registered_module_count': len(modules),
        'registered_script_count': len(scripts),
        'first_pid_count': first[0],
        'second_pid_count': second[0],
        'custody_device': db_device,
        'custody_inode': db_inode,
    }
    return {
        'schema': REPORT_SCHEMA,
        'observation_sha256': hashlib.sha256(
            DOMAIN + _canonical(evidence)).hexdigest(),
        'known_binary_and_fd_inventory_passed': True,
        'enrolled_python_interpreters_observed_live': False,
        'interpreter_process_scan_completed_twice': True,
        'unenrolled_python_versions_excluded': False,
        'unknown_script_and_module_writers_excluded': False,
        'argv_authenticity_proved': False,
        'future_writer_restart_excluded': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def _private_bytes(path, bound):
    # Exact production manifest paths must be private files, not symlinks.
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError('enrolled manifest must be private regular file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_ino != info.st_ino:
            raise InventoryConflict('manifest swapped during open')
        data = os.read(fd, bound+1)
        if len(data) > bound:
            raise ValueError('oversized enrolled manifest')
        return data
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_binary_manifest', type=Path)
    parser.add_argument('trusted_binary_manifest_sha256')
    parser.add_argument('private_interpreted_manifest', type=Path)
    parser.add_argument('trusted_interpreted_manifest_sha256')
    parser.add_argument('custody_database', type=Path)
    parser.add_argument('--db-device', type=int, required=True)
    parser.add_argument('--db-inode', type=int, required=True)
    args = parser.parse_args(argv)
    report = {'schema': REPORT_SCHEMA,
              'witness_fence_retired': False,
              'witness_fence_retirement_authorized': False}
    try:
        if not _mount_is_procfs():
            raise InventoryConflict('kernel procfs mount not verified')
        report.update(inspect(
            _private_bytes(args.private_binary_manifest, MAX_MANIFEST),
            args.trusted_binary_manifest_sha256,
            _private_bytes(args.private_interpreted_manifest,
                           MAX_ENTRYPOINT_MANIFEST),
            args.trusted_interpreted_manifest_sha256,
            args.custody_database, args.db_device, args.db_inode))
        code = 0
    except InventoryConflict:
        report['incomplete_or_live_interpreted_writer'] = True
        code = 1
    except (OSError, ValueError, TypeError, UnicodeError,
            json.JSONDecodeError):
        report['valid_input'] = False
        code = 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
