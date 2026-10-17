"""Stage 263E: advisory Linux service-mask and writer-credential revocation audit.

This read-only check complements signed cgroup quiescence evidence. A unit
mask and inaccessible custody file are point-in-time observations, not a
permanent revocation guarantee. No unlock, kill, mask or DB mutation exists.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import MAX_ORIGINAL_REQUEST
    from .audit_record_witness_fence_quiescence import MAX_STOP
    from .audit_record_witness_linux_quiescence import (
        verify as verify_cgroup, MAX_EVIDENCE, QuiescenceConflict,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import MAX_ORIGINAL_REQUEST
    from audit_record_witness_fence_quiescence import MAX_STOP
    from audit_record_witness_linux_quiescence import (
        verify as verify_cgroup, MAX_EVIDENCE, QuiescenceConflict,
    )

SCHEMA = 'wild-arms-ps1-linux-writer-revocation-observation-v1'
REPORT_SCHEMA = 'wild-arms-ps1-linux-writer-revocation-report-v1'
DOMAIN = b'wild-arms-ps1-linux-writer-revocation-observation-v1\x00'
MAX_UNIT_OUTPUT = 4096
UNIT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,120}\.service\Z')
PROPERTIES = (
    'Id', 'LoadState', 'UnitFileState', 'ActiveState', 'SubState',
    'CanStart', 'NeedDaemonReload', 'MainPID', 'ControlPID',
    'Job', 'FragmentPath',
)
REQUIRED = {
    'LoadState': 'masked',
    'UnitFileState': 'masked',  # runtime-only mask does not qualify
    'ActiveState': 'inactive',
    'SubState': 'dead',
    'CanStart': 'no',
    'NeedDaemonReload': 'no',
    'MainPID': '0',
    'ControlPID': '0',
    'Job': '0',
    'FragmentPath': '/dev/null',
}


class RevocationConflict(QuiescenceConflict):
    """Selected service or file is not observed revoked under strict policy."""


def _unit(unit):
    if type(unit) is not str or not UNIT.fullmatch(unit) or '..' in unit:
        raise ValueError('invalid exact systemd service unit')
    return unit


def _parse_unit(raw, unit):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_UNIT_OUTPUT:
        raise RevocationConflict('invalid bounded systemd observation')
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError as exc:
        raise RevocationConflict('invalid systemd output encoding') from exc
    result = {}
    for line in lines:
        key, sep, value = line.partition('=')
        if not sep or key not in PROPERTIES or key in result:
            raise RevocationConflict('unexpected systemd property')
        result[key] = value
    if set(result) != set(PROPERTIES) or result['Id'] != _unit(unit):
        raise RevocationConflict('systemd unit identity or fields changed')
    for key, value in REQUIRED.items():
        if result[key] != value:
            raise RevocationConflict('systemd unit not durably masked and inactive')
    return result


def _read_systemd(unit):
    # This tool inspects; it NEVER issues systemctl mask/stop/kill/restart.
    command = ['/usr/bin/systemctl', '--system', 'show', '--no-pager']
    for property_name in PROPERTIES:
        command.extend(('-p', property_name))
    command.extend(('--', _unit(unit)))
    proc = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, check=False, timeout=8,
        env={'LC_ALL': 'C', 'LANG': 'C', 'PATH': '/usr/bin:/bin'})
    if proc.returncode != 0:
        raise RevocationConflict('systemd could not authenticate unit state')
    return proc.stdout


def _custody_file(path, *, service_uid, db_device, db_inode):
    """Inspect exact filesystem object via O_NOFOLLOW descriptors."""
    if (type(service_uid) is not int or service_uid <= 0
            or type(db_device) is not int or db_device < 0
            or type(db_inode) is not int or db_inode <= 0):
        raise ValueError('invalid enrolled service UID or custody inode')
    path = Path(path)
    if not path.is_absolute() or path.name in ('.', '..', ''):
        raise ValueError('custody database must have a pinned absolute path')
    pfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = os.fstat(pfd)
        dfd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=pfd)
        try:
            db = os.fstat(dfd)
        finally:
            os.close(dfd)
    finally:
        os.close(pfd)
    if (not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid == service_uid
            or parent.st_mode & 0o077):
        raise RevocationConflict('custody directory accessible to retired UID')
    if (not stat.S_ISREG(db.st_mode)
            or db.st_uid == service_uid
            or db.st_mode & 0o077
            or (db.st_dev, db.st_ino) != (db_device, db_inode)):
        raise RevocationConflict('custody file accessible or object replaced')
    return {
        'custody_device': db.st_dev,
        'custody_inode': db.st_ino,
        'custody_owner_uid': db.st_uid,
        'custody_mode': stat.S_IMODE(db.st_mode),
        'parent_device': parent.st_dev,
        'parent_inode': parent.st_ino,
        'parent_owner_uid': parent.st_uid,
        'parent_mode': stat.S_IMODE(parent.st_mode),
    }


def assess(original_raw, stop_raw, cgroup_evidence_raw,
           supervisor_public, supervisor_pin, *,
           supervisor_tag, cgroup_scope, pinned_boot_id, cgroup_device,
           cgroup_inode, service_unit, service_uid, custody_database,
           db_device, db_inode, systemd_reader=_read_systemd,
           cgroup_root=Path('/sys/fs/cgroup'),
           boot_id_path=Path('/proc/sys/kernel/random/boot_id')):
    """Strict snapshots, never a cryptographic proof of permanent revocation."""
    unit = _unit(service_unit)
    first = _parse_unit(systemd_reader(unit), unit)
    first_db = _custody_file(
        custody_database, service_uid=service_uid,
        db_device=db_device, db_inode=db_inode)
    verified = verify_cgroup(
        original_raw, stop_raw, cgroup_evidence_raw,
        supervisor_public, supervisor_pin, supervisor_tag=supervisor_tag,
        expected_scope=cgroup_scope, pinned_boot_id=pinned_boot_id,
        pinned_device=cgroup_device, pinned_inode=cgroup_inode,
        cgroup_root=cgroup_root, boot_id_path=boot_id_path)
    second = _parse_unit(systemd_reader(unit), unit)
    second_db = _custody_file(
        custody_database, service_uid=service_uid,
        db_device=db_device, db_inode=db_inode)
    if first != second or first_db != second_db:
        raise RevocationConflict('unit or custody file changed during observation')
    if verified['witness_fence_retirement_authorized'] is not False:
        raise RevocationConflict('unsafe upstream cgroup decision')
    observation = {
        'schema': SCHEMA,
        'signed_cgroup_observation_sha256': hashlib.sha256(
            cgroup_evidence_raw).hexdigest(),
        'systemd_service_unit': unit,
        'enrolled_service_uid': service_uid,
        'systemd_properties': first,
        'filesystem_identity': first_db,
        'pinned_boot_id': pinned_boot_id,
    }
    return {
        'schema': REPORT_SCHEMA,
        'observation_sha256': hashlib.sha256(
            DOMAIN + _canonical(observation)).hexdigest(),
        'systemd_unit_masked_and_inactive_at_observation': True,
        'enrolled_service_uid_denied_by_basic_file_modes': True,
        'signed_cgroup_snapshot_reverified': True,
        'alternate_processes_or_privileged_writers_excluded': False,
        'durable_global_writer_revocation_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'production_quiescence_proved': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_private_request', type=Path)
    parser.add_argument('signed_supervisor_stop_claim', type=Path)
    parser.add_argument('private_cgroup_observation', type=Path)
    parser.add_argument('pinned_supervisor_public_pem', type=Path)
    parser.add_argument('trusted_supervisor_pem_sha256')
    parser.add_argument('custody_database', type=Path)
    parser.add_argument('--supervisor-tag', required=True)
    parser.add_argument('--cgroup-scope', required=True)
    parser.add_argument('--pinned-boot-id', required=True)
    parser.add_argument('--cgroup-device', type=int, required=True)
    parser.add_argument('--cgroup-inode', type=int, required=True)
    parser.add_argument('--service-unit', required=True)
    parser.add_argument('--service-uid', type=int, required=True)
    parser.add_argument('--db-device', type=int, required=True)
    parser.add_argument('--db-inode', type=int, required=True)
    args = parser.parse_args(argv)
    report = {'schema': REPORT_SCHEMA,
              'witness_fence_retired': False,
              'witness_fence_retirement_authorized': False}
    try:
        # This host is not trusted merely because it can emit a report.
        from tools.audit_record_witness_linux_quiescence import _kernel_mount_verified
        if not _kernel_mount_verified():
            raise RevocationConflict('cgroup v2 kernel mount not observed')
        report.update(assess(
            _read_limited(_private_regular_file(args.original_private_request),
                          MAX_ORIGINAL_REQUEST),
            _read_limited(_private_regular_file(args.signed_supervisor_stop_claim),
                          MAX_STOP),
            _read_limited(_private_regular_file(args.private_cgroup_observation),
                          MAX_EVIDENCE),
            args.pinned_supervisor_public_pem, args.trusted_supervisor_pem_sha256,
            supervisor_tag=args.supervisor_tag, cgroup_scope=args.cgroup_scope,
            pinned_boot_id=args.pinned_boot_id,
            cgroup_device=args.cgroup_device, cgroup_inode=args.cgroup_inode,
            service_unit=args.service_unit, service_uid=args.service_uid,
            custody_database=args.custody_database,
            db_device=args.db_device, db_inode=args.db_inode))
        code = 0
    except RevocationConflict:
        report['service_or_writer_access_not_revoked'] = True
        code = 1
    except (ValueError, KeyError, TypeError, OSError,
            UnicodeError, subprocess.SubprocessError):
        report['valid_input'] = False
        code = 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
