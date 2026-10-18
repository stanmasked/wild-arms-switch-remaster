"""Stage 263N: independent accepted-head registry for two-admin checkpoints.

Accept a Stage 263M two-signer checkpoint only if it extends the current
registered checkpoint SHA and an externally pinned registry (count, head).
Append one event in a single BEGIN IMMEDIATE transaction, rejecting competing
branches, old checkpoints, duplicate nonces and stale operator pins.

The registry is another SQLite file. Independent off-host storage of its
latest (count, head, checkpoint) is a REQUIRED OPERATOR ACTION, not something
this program can attest. No fence retirement or reconciliation API.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_run_replay_ledger import (
        _private_path, _check_expected as _check_registry_pin,
        MAX_EVENTS,
    )
    from .audit_record_witness_replay_head_checkpoint import (
        verify as verify_two_admin, SCHEMA as HEAD_SCHEMA,
        DOMAIN as HEAD_DOMAIN, ANCHOR_GENESIS, CheckpointConflict,
        MAX_SIGNED, HEX64, TAG,
    )
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_run_replay_ledger import (
        _private_path, _check_expected as _check_registry_pin,
        MAX_EVENTS,
    )
    from audit_record_witness_replay_head_checkpoint import (
        verify as verify_two_admin, SCHEMA as HEAD_SCHEMA,
        DOMAIN as HEAD_DOMAIN, ANCHOR_GENESIS, CheckpointConflict,
        MAX_SIGNED, HEX64, TAG,
    )
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA = 'wild-arms-ps1-accepted-replay-checkpoint-registry-v1'
REPORT_SCHEMA = 'wild-arms-ps1-accepted-replay-checkpoint-registry-report-v1'
DOMAIN = b'wild-arms-ps1-accepted-replay-checkpoint-registry-v1\x00'
GENESIS = hashlib.sha256(DOMAIN + b'genesis').hexdigest()
MARKER = 0x41435247  # ACRG
MAX_CHECKPOINTS = MAX_EVENTS
CREATE_SQL = """CREATE TABLE accepted_replay_checkpoints (
    sequence INTEGER PRIMARY KEY,
    schema TEXT NOT NULL,
    checkpoint_tag TEXT NOT NULL,
    previous_registry_sha256 TEXT NOT NULL,
    previous_checkpoint_sha256 TEXT NOT NULL,
    checkpoint_sha256 TEXT NOT NULL,
    replay_event_count INTEGER NOT NULL,
    replay_head_sha256 TEXT NOT NULL,
    checkpoint_nonce TEXT NOT NULL,
    admin_a_key_sha256 TEXT NOT NULL,
    admin_b_key_sha256 TEXT NOT NULL,
    admin_a_signed_sha256 TEXT NOT NULL,
    admin_b_signed_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL
)"""
COLUMNS = (
    'sequence','schema','checkpoint_tag','previous_registry_sha256',
    'previous_checkpoint_sha256','checkpoint_sha256','replay_event_count',
    'replay_head_sha256','checkpoint_nonce','admin_a_key_sha256',
    'admin_b_key_sha256','admin_a_signed_sha256','admin_b_signed_sha256',
    'event_sha256',
)


class RegistryConflict(ValueError):
    """Incorrect checkpoint predecessor, external anchor or event chain."""


def _hex64(value):
    if type(value) is not str or not HEX64.fullmatch(value):
        raise RegistryConflict('invalid independently pinned 64-hex value')
    return value


def _connect(path):
    # No accidental recreation of a deleted SQLite journal.
    uri = 'file:' + quote(str(path), safe='/') + '?mode=rw'
    con = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=8)
    con.execute('PRAGMA busy_timeout=8000')
    con.execute('PRAGMA synchronous=FULL')
    return con


def _audit(con):
    if con.execute('PRAGMA user_version').fetchone()[0] != MARKER:
        raise RegistryConflict('accepted checkpoint registry seal changed')
    tables = con.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()
    if tables != [('accepted_replay_checkpoints', CREATE_SQL)]:
        raise RegistryConflict('unexpected accepted checkpoint registry schema')
    names = tuple(row[1] for row in
                  con.execute('PRAGMA table_info(accepted_replay_checkpoints)'))
    if names != COLUMNS:
        raise RegistryConflict('accepted checkpoint columns changed')
    rows = con.execute(
        'SELECT '+','.join(COLUMNS)+' FROM accepted_replay_checkpoints '
        'ORDER BY sequence').fetchall()
    if len(rows) > MAX_CHECKPOINTS:
        raise RegistryConflict('checkpoint registry exceeds audited bound')
    previous = GENESIS
    previous_checkpoint = ANCHOR_GENESIS
    previous_count = -1
    first_tag = None
    seen_nonces = set()
    seen_checkpoints = set()
    for sequence, row in enumerate(rows, 1):
        entry = dict(zip(COLUMNS, row))
        if (type(entry['sequence']) is not int
                or entry['sequence'] != sequence
                or entry['schema'] != SCHEMA
                or type(entry['checkpoint_tag']) is not str
                or not TAG.fullmatch(entry['checkpoint_tag'])
                or type(entry['replay_event_count']) is not int
                or entry['replay_event_count'] <= previous_count
                or entry['replay_event_count'] > MAX_EVENTS
                or type(entry['checkpoint_nonce']) is not str
                or len(entry['checkpoint_nonce']) != 32
                or any(c not in '0123456789abcdef'
                       for c in entry['checkpoint_nonce'])
                or any(not _hex64(entry[k]) for k in (
                    'previous_registry_sha256','previous_checkpoint_sha256',
                    'checkpoint_sha256','replay_head_sha256',
                    'admin_a_key_sha256','admin_b_key_sha256',
                    'admin_a_signed_sha256','admin_b_signed_sha256',
                    'event_sha256'))
                or entry['admin_a_key_sha256'] == entry['admin_b_key_sha256']
                or entry['previous_registry_sha256'] != previous
                or entry['previous_checkpoint_sha256'] != previous_checkpoint
                or entry['checkpoint_nonce'] in seen_nonces
                or entry['checkpoint_sha256'] in seen_checkpoints
                or (first_tag is not None
                    and entry['checkpoint_tag'] != first_tag)):
            raise RegistryConflict('branched, reused or malformed checkpoint history')
        expected = hashlib.sha256(
            DOMAIN + _canonical({k:entry[k] for k in COLUMNS[:-1]})).hexdigest()
        if not hmac.compare_digest(expected, entry['event_sha256']):
            raise RegistryConflict('accepted checkpoint event hash changed')
        seen_nonces.add(entry['checkpoint_nonce'])
        seen_checkpoints.add(entry['checkpoint_sha256'])
        previous = entry['event_sha256']
        previous_checkpoint = entry['checkpoint_sha256']
        previous_count = entry['replay_event_count']
        first_tag = entry['checkpoint_tag']
    return len(rows), previous, previous_checkpoint, previous_count, first_tag, seen_nonces


def _status(count, head, checkpoint, *, initialized=False, accepted=False):
    return {
        'schema': REPORT_SCHEMA,
        'registry_event_count': count,
        'registry_head_sha256': head,
        'latest_checkpoint_sha256': checkpoint,
        'new_registry_created': initialized,
        'two_admin_head_accepted_once': accepted,
        'external_latest_registry_escrow_proved': False,
        'durable_hardware_rollback_prevention_proved': False,
        'global_writer_revocation_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def initialize(path):
    path = _private_path(path, exists=False)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(fd)
    # A failure leaves the partial journal in place for independent recovery.
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(CREATE_SQL)
            con.execute('PRAGMA user_version='+str(MARKER))
            con.commit()
            state = _audit(con)
            if state[:3] != (0, GENESIS, ANCHOR_GENESIS):
                raise RegistryConflict('fresh registry genesis differs')
        except Exception:
            con.rollback()
            raise
    return _status(0, GENESIS, ANCHOR_GENESIS, initialized=True)


def inspect(path, expected_count, expected_head, expected_checkpoint):
    """Read-only inspection against ALL externally escrowed latest values."""
    _hex64(expected_checkpoint)
    path = _private_path(path, exists=True)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count, head, checkpoint, _, _, _ = _audit(con)
            _check_registry_pin(count, head, expected_count, expected_head)
            if not hmac.compare_digest(checkpoint, expected_checkpoint):
                raise RegistryConflict('latest checkpoint differs from external escrow')
        finally:
            con.rollback()
    return _status(count, head, checkpoint)


def accept(path, replay_journal, signed_a, signed_b,
           public_a, public_a_pin, public_b, public_b_pin, *,
           checkpoint_tag, prior_checkpoint_pin, candidate_checkpoint_pin,
           expected_registry_count, expected_registry_head,
           expected_latest_checkpoint_pin):
    """Verify signatures; atomic CAS acceptance of ONE monotonic checkpoint."""
    _hex64(expected_latest_checkpoint_pin)
    _hex64(expected_registry_head)
    candidate = verify_two_admin(
        replay_journal, signed_a, signed_b,
        public_a, public_a_pin, public_b, public_b_pin,
        checkpoint_tag=checkpoint_tag,
        prior_checkpoint_pin=prior_checkpoint_pin,
        independently_pinned_checkpoint_sha256=candidate_checkpoint_pin)
    if candidate['witness_fence_retirement_authorized'] is not False:
        raise RegistryConflict('unexpected upstream release authorization')
    a = _signed(signed_a, HEAD_SCHEMA, HEAD_DOMAIN, public_a_pin, public_a)
    b = _signed(signed_b, HEAD_SCHEMA, HEAD_DOMAIN, public_b_pin, public_b)
    # No case-insensitive aliasing or untrusted role supplied by the caller.
    if (a['admin_role'] != 'admin-a' or b['admin_role'] != 'admin-b'
            or a['checkpoint_nonce'] != b['checkpoint_nonce']):
        raise RegistryConflict('inconsistent checkpoint signers')

    path = _private_path(path, exists=True)
    if Path(path).resolve() == Path(replay_journal).resolve():
        raise RegistryConflict('registry cannot be same file as replay journal')
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count, head, latest, last_replay_count, scope, seen = _audit(con)
            _check_registry_pin(
                count, head, expected_registry_count, expected_registry_head)
            if (not hmac.compare_digest(latest, expected_latest_checkpoint_pin)
                    or not hmac.compare_digest(latest, prior_checkpoint_pin)):
                raise RegistryConflict('stale checkpoint parent or external tip')
            if (count >= MAX_CHECKPOINTS
                    or a['checkpoint_nonce'] in seen
                    or (scope is not None and scope != checkpoint_tag)
                    or candidate['checkpoint_event_count'] <= last_replay_count):
                raise RegistryConflict('replayed or nonmonotonic accepted head')
            event = {
                'sequence': count+1,
                'schema': SCHEMA,
                'checkpoint_tag': checkpoint_tag,
                'previous_registry_sha256': head,
                'previous_checkpoint_sha256': latest,
                'checkpoint_sha256': candidate['checkpoint_sha256'],
                'replay_event_count': candidate['checkpoint_event_count'],
                'replay_head_sha256': a['ledger_head_sha256'],
                'checkpoint_nonce': a['checkpoint_nonce'],
                'admin_a_key_sha256': public_a_pin,
                'admin_b_key_sha256': public_b_pin,
                'admin_a_signed_sha256': hashlib.sha256(signed_a).hexdigest(),
                'admin_b_signed_sha256': hashlib.sha256(signed_b).hexdigest(),
            }
            event_hash = hashlib.sha256(
                DOMAIN + _canonical(event)).hexdigest()
            con.execute(
                'INSERT INTO accepted_replay_checkpoints VALUES '
                '(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (*event.values(), event_hash))
            updated = _audit(con)
            if (updated[0] != count+1
                    or not hmac.compare_digest(updated[1], event_hash)
                    or updated[2] != candidate['checkpoint_sha256']):
                raise RegistryConflict('atomic checkpoint acceptance audit failed')
            con.commit()
        except Exception:
            con.rollback()
            raise
    return _status(count+1, event_hash,
                   candidate['checkpoint_sha256'], accepted=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='action', required=True)
    init = modes.add_parser('init')
    init.add_argument('private_registry', type=Path)
    inspect_parser = modes.add_parser('inspect')
    inspect_parser.add_argument('private_registry', type=Path)
    inspect_parser.add_argument('--expected-count', type=int, required=True)
    inspect_parser.add_argument('--expected-head', required=True)
    inspect_parser.add_argument('--expected-checkpoint', required=True)
    accept_parser = modes.add_parser('accept')
    accept_parser.add_argument('private_registry', type=Path)
    accept_parser.add_argument('private_replay_journal', type=Path)
    accept_parser.add_argument('admin_a_signed', type=Path)
    accept_parser.add_argument('admin_a_public', type=Path)
    accept_parser.add_argument('admin_a_public_pin')
    accept_parser.add_argument('admin_b_signed', type=Path)
    accept_parser.add_argument('admin_b_public', type=Path)
    accept_parser.add_argument('admin_b_public_pin')
    accept_parser.add_argument('--checkpoint-tag', required=True)
    accept_parser.add_argument('--prior-checkpoint-sha256', required=True)
    accept_parser.add_argument('--candidate-checkpoint-sha256', required=True)
    accept_parser.add_argument('--expected-count', type=int, required=True)
    accept_parser.add_argument('--expected-head', required=True)
    accept_parser.add_argument('--expected-checkpoint', required=True)
    args = parser.parse_args(argv)
    report = {'schema': REPORT_SCHEMA,
              'witness_fence_retirement_authorized': False,
              'witness_fence_retired': False}
    try:
        if args.action == 'init':
            report.update(initialize(args.private_registry))
        elif args.action == 'inspect':
            report.update(inspect(
                args.private_registry, args.expected_count,
                args.expected_head, args.expected_checkpoint))
        else:
            def rd(path):
                return _read_limited(_private_regular_file(path), MAX_SIGNED)
            report.update(accept(
                args.private_registry, args.private_replay_journal,
                rd(args.admin_a_signed), rd(args.admin_b_signed),
                args.admin_a_public, args.admin_a_public_pin,
                args.admin_b_public, args.admin_b_public_pin,
                checkpoint_tag=args.checkpoint_tag,
                prior_checkpoint_pin=args.prior_checkpoint_sha256,
                candidate_checkpoint_pin=args.candidate_checkpoint_sha256,
                expected_registry_count=args.expected_count,
                expected_registry_head=args.expected_head,
                expected_latest_checkpoint_pin=args.expected_checkpoint))
        code = 0
    except (RegistryConflict, CheckpointConflict):
        report['checkpoint_registry_conflict'] = True
        code = 1
    except (OSError, ValueError, TypeError, KeyError, IndexError, sqlite3.Error):
        report['valid_input'] = False
        code = 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
