"""Linux cgroup v2 *advisory* quiescence evidence for a fenced custody writer.

Observes an enrolled cgroup's frozen/empty state, boot identity and inode
without changing process state. This is not independently enforced writer
revocation: stale writers elsewhere, service restarts and privilege escalation
can bypass a cgroup snapshot. NEVER authorizes a witness fence release.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _parse, _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file, _write_new_private
    from .audit_record_witness_fence_reconciliation import (
        _original, _request_digest, MAX_ORIGINAL_REQUEST,
    )
    from .audit_record_witness_fence_quiescence import (
        _verified_stop, MAX_STOP,
    )
    from .audit_record_witness_fence import _owner
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _parse, _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file, _write_new_private
    from audit_record_witness_fence_reconciliation import (
        _original, _request_digest, MAX_ORIGINAL_REQUEST,
    )
    from audit_record_witness_fence_quiescence import (
        _verified_stop, MAX_STOP,
    )
    from audit_record_witness_fence import _owner

SCHEMA = 'wild-arms-ps1-linux-cgroup-quiescence-observation-v1'
REPORT_SCHEMA = 'wild-arms-ps1-linux-cgroup-quiescence-report-v1'
DOMAIN = b'wild-arms-ps1-linux-cgroup-quiescence-observation-v1\x00'
MAX_NODES = 128
MAX_EVIDENCE = 32768
MAX_FILE = 16384
_HEX32 = re.compile(r'[0-9a-f]{32}\Z')
_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
_PART = re.compile(r'[A-Za-z0-9_.@:-]{1,128}\Z')


class QuiescenceConflict(ValueError):
    """Cgroup identity, observed process state or signed evidence differs."""


def _scope(value):
    if (type(value) is not str or not value or len(value) > 512
            or any(not _PART.fullmatch(part) or part in ('.', '..')
                   for part in value.split('/'))):
        raise ValueError('invalid bounded relative cgroup v2 scope')
    return value


def _read_at(fd, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise QuiescenceConflict('cgroup control is not a regular file')
        raw = os.read(descriptor, MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise QuiescenceConflict('oversized cgroup control file')
        return raw.decode('ascii', errors='strict')
    finally:
        os.close(descriptor)


def _events(fd):
    fields = {}
    for line in _read_at(fd, 'cgroup.events').splitlines():
        parts = line.split()
        if (len(parts) != 2 or parts[0] in fields
                or not parts[1].isdigit()):
            raise QuiescenceConflict('malformed cgroup event fields')
        fields[parts[0]] = int(parts[1])
    if fields.get('populated') != 0 or fields.get('frozen') != 1:
        raise QuiescenceConflict('cgroup not observed frozen and unpopulated')
    return fields


def _observe_tree(fd, base):
    seen = []
    def walk(directory, rel):
        if len(seen) >= MAX_NODES:
            raise QuiescenceConflict('cgroup subtree exceeds observation bound')
        identity = os.fstat(directory)
        events = _events(directory)
        if (_read_at(directory, 'cgroup.procs').strip()
                or _read_at(directory, 'cgroup.threads').strip()):
            raise QuiescenceConflict('live processes or threads in custody cgroup')
        if rel == base and _read_at(directory, 'cgroup.freeze').strip() != '1':
            raise QuiescenceConflict('custody cgroup freeze flag not set')
        seen.append({
            'relative_path': rel,
            'device': identity.st_dev,
            'inode': identity.st_ino,
            'frozen': events['frozen'],
            'populated': events['populated'],
        })
        with os.scandir(directory) as entries:
            children = []
            for entry in entries:
                if entry.is_symlink():
                    raise QuiescenceConflict('symlink in cgroup subtree')
                if entry.is_dir(follow_symlinks=False):
                    if not _PART.fullmatch(entry.name):
                        raise QuiescenceConflict('invalid cgroup child name')
                    children.append(entry.name)
        for name in sorted(children):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            try:
                walk(child, rel + '/' + name)
            finally:
                os.close(child)
    walk(fd, base)
    return seen


def _kernel_mount_verified():
    # CLI only: never allow a fake directory to masquerade as production
    # cgroupfs. A caller with privileged mount-namespace control is still
    # outside this verifier's trust boundary.
    with open('/proc/self/mountinfo', 'r', encoding='utf-8') as inp:
        for line in inp:
            left, separator, right = line.partition(' - ')
            if not separator:
                continue
            fields = left.split()
            fstype = right.split()[0] if right.split() else ''
            if len(fields) >= 5 and fields[4] == '/sys/fs/cgroup':
                return fstype == 'cgroup2'
    return False


def _snapshot(scope, *, cgroup_root, boot_id_path):
    scope = _scope(scope)
    boot_id = Path(boot_id_path).read_text(encoding='ascii').strip()
    if not _UUID.fullmatch(boot_id):
        raise QuiescenceConflict('invalid kernel boot identity')
    with ExitStack() as stack:
        fd = os.open(cgroup_root,
                     os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        for part in scope.split('/'):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            stack.callback(os.close, child)
            fd = child
        first = _observe_tree(fd, scope)
        second = _observe_tree(fd, scope)
        if first != second:
            raise QuiescenceConflict('cgroup subtree changed during observation')
    return boot_id, first


def observe(original_raw, session_nonce, scope, pinned_boot_id,
            pinned_device, pinned_inode, *,
            cgroup_root=Path('/sys/fs/cgroup'),
            boot_id_path=Path('/proc/sys/kernel/random/boot_id')):
    """Produce a bounded read-only snapshot tied to exact original request."""
    request, _ = _original(original_raw)
    if type(session_nonce) is not str or not _HEX32.fullmatch(session_nonce):
        raise ValueError('invalid fresh supervisor stop-session nonce')
    if type(pinned_boot_id) is not str or not _UUID.fullmatch(pinned_boot_id):
        raise ValueError('invalid independently enrolled boot ID')
    if (type(pinned_device) is not int or pinned_device < 0
            or type(pinned_inode) is not int or pinned_inode <= 0):
        raise ValueError('invalid enrolled cgroup device/inode')
    boot_id, nodes = _snapshot(scope, cgroup_root=cgroup_root,
                               boot_id_path=boot_id_path)
    if (boot_id != pinned_boot_id
            or nodes[0]['device'] != pinned_device
            or nodes[0]['inode'] != pinned_inode):
        raise QuiescenceConflict('cgroup instance is not independently pinned')
    result = {
        'schema': SCHEMA,
        'custody_request_sha256': _request_digest(original_raw),
        'fence_owner_sha256': _owner(request['request_id']),
        'stop_session_nonce': session_nonce,
        'boot_id': boot_id,
        'scope': _scope(scope),
        'nodes': nodes,
    }
    if len(_canonical(result)) > MAX_EVIDENCE:
        raise QuiescenceConflict('cgroup observation exceeds evidence bound')
    return result


def evidence_sha256(result):
    if type(result) is not dict or result.get('schema') != SCHEMA:
        raise ValueError('unexpected Linux cgroup observation')
    return hashlib.sha256(DOMAIN + _canonical(result)).hexdigest()


def verify(original_raw, signed_stop_raw, evidence_raw,
           supervisor_public, supervisor_pin, *, supervisor_tag,
           expected_scope, pinned_boot_id, pinned_device, pinned_inode,
           cgroup_root=Path('/sys/fs/cgroup'),
           boot_id_path=Path('/proc/sys/kernel/random/boot_id')):
    """Check signed binding AND recapture; never confer safe release."""
    if (type(evidence_raw) is not bytes or not 0 < len(evidence_raw) <= MAX_EVIDENCE):
        raise ValueError('invalid bounded cgroup observation')
    saved = _parse(evidence_raw)
    if type(saved) is not dict or evidence_raw != _canonical(saved):
        raise ValueError('noncanonical cgroup observation')
    signed = _verified_stop(
        original_raw, signed_stop_raw, supervisor_public, supervisor_pin,
        supervisor_tag)
    if (saved.get('stop_session_nonce') != signed['stop_session_nonce']
            or evidence_sha256(saved) != signed['control_evidence_sha256']):
        raise QuiescenceConflict('signed stop claim not bound to cgroup evidence')
    current = observe(
        original_raw, signed['stop_session_nonce'], expected_scope,
        pinned_boot_id, pinned_device, pinned_inode,
        cgroup_root=cgroup_root, boot_id_path=boot_id_path)
    if saved != current:
        raise QuiescenceConflict('cgroup evidence stale or changed')
    return {
        'schema': REPORT_SCHEMA,
        'signed_supervisor_claim_binds_observed_cgroup': True,
        'enrolled_boot_and_cgroup_identity_match': True,
        'frozen_and_empty_at_observation': True,
        'external_writer_revocation_proved': False,
        'all_possible_writer_processes_excluded': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'production_quiescence_proved': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    for mode in ('observe', 'verify'):
        p = modes.add_parser(mode)
        p.add_argument('original_private_request', type=Path)
        if mode == 'observe':
            p.add_argument('stop_session_nonce')
            p.add_argument('private_observation_output', type=Path)
        else:
            p.add_argument('signed_supervisor_stop_claim', type=Path)
            p.add_argument('private_observation', type=Path)
            p.add_argument('pinned_supervisor_public_pem', type=Path)
            p.add_argument('trusted_supervisor_pem_sha256')
            p.add_argument('--supervisor-tag', required=True)
        p.add_argument('--scope', required=True)
        p.add_argument('--pinned-boot-id', required=True)
        p.add_argument('--pinned-device', type=int, required=True)
        p.add_argument('--pinned-inode', type=int, required=True)
    args = parser.parse_args(argv)
    report = {'schema': REPORT_SCHEMA, 'witness_fence_retired': False,
              'witness_fence_retirement_authorized': False}
    try:
        if not _kernel_mount_verified():
            raise QuiescenceConflict('Linux cgroup v2 mount not observed')
        original = _read_limited(_private_regular_file(
            args.original_private_request), MAX_ORIGINAL_REQUEST)
        shared = dict(expected_scope=args.scope, pinned_boot_id=args.pinned_boot_id,
                      pinned_device=args.pinned_device, pinned_inode=args.pinned_inode)
        if args.mode == 'observe':
            evidence = observe(
                original, args.stop_session_nonce, shared['expected_scope'],
                shared['pinned_boot_id'], shared['pinned_device'],
                shared['pinned_inode'])
            _write_new_private(args.private_observation_output,
                               _canonical(evidence))
            report['private_cgroup_observation_created'] = True
            report['observation_sha256'] = evidence_sha256(evidence)
        else:
            report.update(verify(
                original,
                _read_limited(_private_regular_file(
                    args.signed_supervisor_stop_claim), MAX_STOP),
                _read_limited(_private_regular_file(
                    args.private_observation), MAX_EVIDENCE),
                args.pinned_supervisor_public_pem,
                args.trusted_supervisor_pem_sha256,
                supervisor_tag=args.supervisor_tag, **shared))
        code = 0
    except QuiescenceConflict:
        report['linux_cgroup_observation_conflict'] = True
        code = 1
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        report['valid_input'] = False
        code = 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
