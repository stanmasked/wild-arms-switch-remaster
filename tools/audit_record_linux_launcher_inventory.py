"""Stage 263H: fail-closed audit of alternative script and module launchers.

Enrolled shells, env wrappers and other runtimes are matched by kernel exe
path. All /proc cmdlines are checked for enrolled absolute custody scripts
and exact ' -m module' invocations, including processes using an unknown
interpreter. This is a bounded observation, not complete runtime coverage
or proof of future writer revocation. NEVER release a witness fence.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat

try:
    from .audit_record_linux_writer_inventory import (
        _canonical, _strict_json, _abs_path, _SHA256, _PID,
        _read_executable, _read_at, _process_identity, _target_inodes,
        _mount_is_procfs, InventoryConflict, MAX_PIDS, MAX_WRITERS,
    )
    from .audit_record_linux_interpreted_writers import (
        inspect as inspect_python, _bounded_argv, _MODULE, _private_bytes,
        MAX_CMDLINE,
        MAX_ENTRYPOINT_MANIFEST,
    )
    from .audit_record_linux_writer_inventory import MAX_MANIFEST
except ImportError:
    from audit_record_linux_writer_inventory import (
        _canonical, _strict_json, _abs_path, _SHA256, _PID,
        _read_executable, _process_identity, _target_inodes,
        _mount_is_procfs, InventoryConflict, MAX_PIDS, MAX_WRITERS,
    )
    from audit_record_linux_interpreted_writers import (
        inspect as inspect_python, _bounded_argv, _MODULE, _private_bytes,
        MAX_ENTRYPOINT_MANIFEST,
    )
    from audit_record_linux_writer_inventory import MAX_MANIFEST

SCHEMA = 'wild-arms-ps1-known-custody-alternative-launchers-v1'
REPORT_SCHEMA = 'wild-arms-ps1-linux-alternative-launcher-report-v1'
DOMAIN = b'wild-arms-ps1-linux-alternative-launcher-report-v1\x00'
MAX_LAUNCH_MANIFEST = 16384


def _sorted_names(items, validator):
    if type(items) is not list or len(items) > MAX_WRITERS:
        raise ValueError('invalid bounded launcher manifest collection')
    checked = []
    for item in items:
        if type(item) is not str or not validator(item):
            raise ValueError('invalid enrolled launcher entrypoint')
        checked.append(item)
    if checked != sorted(set(checked)):
        raise ValueError('launcher entrypoints must be sorted and unique')
    return tuple(checked)


def _launchers(raw, independent_pin):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_LAUNCH_MANIFEST
            or type(independent_pin) is not str
            or not _SHA256.fullmatch(independent_pin)):
        raise ValueError('invalid bounded enrolled alternative launcher manifest')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), independent_pin):
        raise InventoryConflict('alternative launcher inventory pin mismatch')
    body = _strict_json(raw)
    if (type(body) is not dict
            or set(body) != {'schema', 'launchers', 'modules', 'scripts'}
            or body['schema'] != SCHEMA or raw != _canonical(body)):
        raise ValueError('invalid canonical alternative launcher inventory')
    binaries = body['launchers']
    if (type(binaries) is not list or not 0 < len(binaries) <= MAX_WRITERS):
        raise ValueError('alternative launcher catalogue cannot be empty')
    previous = ''
    paths = []
    for item in binaries:
        if (type(item) is not dict or set(item) != {'path', 'sha256'}
                or type(item['sha256']) is not str
                or not _SHA256.fullmatch(item['sha256'])):
            raise ValueError('invalid exact alternative launcher enrollment')
        path = _abs_path(item['path'])
        if path <= previous:
            raise ValueError('alternative launcher executable list unsorted')
        paths.append(path)
        previous = path
    modules = _sorted_names(
        body['modules'], lambda value: bool(_MODULE.fullmatch(value)))
    scripts = _sorted_names(
        body['scripts'], lambda value: _safe_script(value))
    if not modules and not scripts:
        raise ValueError('no enrolled scripts or modules')
    return tuple(paths), modules, scripts


def _safe_script(path):
    try:
        _abs_path(path)
    except ValueError:
        return False
    return True


def _matches(argv, modules, scripts):
    """Exact NUL-delimited argv token comparison, not substring matching."""
    for idx, part in enumerate(argv):
        if part in scripts:
            return True
        if (part == '-m' and idx + 1 < len(argv)
                and argv[idx+1] in modules):
            return True
    return False


def _scan(proc_root, enrolled_launchers, modules, scripts):
    root = os.open(proc_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with os.scandir(root) as entries:
            pids = sorted(int(entry.name) for entry in entries
                          if _PID.fullmatch(entry.name))
        if len(pids) > MAX_PIDS:
            raise InventoryConflict('process count exceeds scan bound')
        possible_writers = []
        for pid in pids:
            fd = os.open(str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=root)
            try:
                started = _process_identity(fd, pid)
                exe = _read_executable(fd)
                # Kernel threads have no userspace exe/cmdline. For every
                # observable userspace process, require bounded argv.
                if exe is None:
                    # The only exception is a genuine kernel thread with
                    # *empty* procfs cmdline. Missing or malformed data
                    # must not be interpreted as proof of a kernel thread.
                    if _read_at(fd, 'cmdline', MAX_CMDLINE):
                        raise InventoryConflict('unbound userspace process exe')
                    argv = ()
                else:
                    argv = _bounded_argv(fd)
                matching = (exe in enrolled_launchers
                            or (argv and _matches(argv, modules, scripts)))
                if _process_identity(fd, pid) != started:
                    raise InventoryConflict('PID identity changed while scanning')
                if matching:
                    possible_writers.append(pid)
            finally:
                os.close(fd)
        return len(pids), possible_writers
    except (OSError, UnicodeError, ProcessLookupError) as exc:
        raise InventoryConflict('incomplete alternative launcher procfs scan') from exc
    finally:
        os.close(root)


def inspect(binary_raw, binary_pin, python_raw, python_pin, launcher_raw,
            launcher_pin, db_path, db_device, db_inode, *,
            proc_root=Path('/proc')):
    """Conservative union of native, Python and alternative launch paths."""
    paths, modules, scripts = _launchers(launcher_raw, launcher_pin)
    python_result = inspect_python(
        binary_raw, binary_pin, python_raw, python_pin,
        db_path, db_device, db_inode, proc_root=proc_root)
    before = _target_inodes(db_path, db_device, db_inode)
    first = _scan(proc_root, paths, modules, scripts)
    middle = _target_inodes(db_path, db_device, db_inode)
    second = _scan(proc_root, paths, modules, scripts)
    after = _target_inodes(db_path, db_device, db_inode)
    if before != middle or middle != after:
        raise InventoryConflict('custody inode or SQLite sidecars changed')
    if first[1] or second[1]:
        raise InventoryConflict('enrolled alternative writer remains active')
    evidence = {
        'schema': REPORT_SCHEMA,
        'python_inventory_sha256': python_result['observation_sha256'],
        'alternative_manifest_sha256': hashlib.sha256(launcher_raw).hexdigest(),
        'launcher_count': len(paths),
        'module_count': len(modules),
        'script_count': len(scripts),
        'first_pid_count': first[0],
        'second_pid_count': second[0],
        'custody_device': db_device,
        'custody_inode': db_inode,
    }
    return {
        'schema': REPORT_SCHEMA,
        'observation_sha256': hashlib.sha256(
            DOMAIN + _canonical(evidence)).hexdigest(),
        'native_and_python_inventory_passed': True,
        'enrolled_alternative_launchers_observed': False,
        'known_script_or_module_argv_observed': False,
        'alternative_launcher_procfs_scanned_twice': True,
        'all_alternative_runtimes_excluded': False,
        'argv_is_authenticated_provenance': False,
        'future_writer_launch_prevented': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_binary_manifest', type=Path)
    parser.add_argument('trusted_binary_manifest_sha256')
    parser.add_argument('private_python_manifest', type=Path)
    parser.add_argument('trusted_python_manifest_sha256')
    parser.add_argument('private_launcher_manifest', type=Path)
    parser.add_argument('trusted_launcher_manifest_sha256')
    parser.add_argument('custody_database', type=Path)
    parser.add_argument('--db-device', type=int, required=True)
    parser.add_argument('--db-inode', type=int, required=True)
    args = parser.parse_args(argv)
    report = {'schema': REPORT_SCHEMA,
              'witness_fence_retirement_authorized': False,
              'witness_fence_retired': False}
    try:
        if not _mount_is_procfs():
            raise InventoryConflict('kernel procfs mount cannot be confirmed')
        result = inspect(
            _private_bytes(args.private_binary_manifest, MAX_MANIFEST),
            args.trusted_binary_manifest_sha256,
            _private_bytes(args.private_python_manifest, MAX_ENTRYPOINT_MANIFEST),
            args.trusted_python_manifest_sha256,
            _private_bytes(args.private_launcher_manifest, MAX_LAUNCH_MANIFEST),
            args.trusted_launcher_manifest_sha256,
            args.custody_database, args.db_device, args.db_inode)
        report.update(result)
        code = 0
    except InventoryConflict:
        report['inventory_incomplete_or_writer_detected'] = True
        code = 1
    except (OSError, ValueError, TypeError, UnicodeError,
            json.JSONDecodeError):
        report['valid_input'] = False
        code = 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
