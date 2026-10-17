"""Read-only continuity checks against a separately retained private checkpoint.

A checkpoint stores *hashed logical row commitments*, not raw nonces, game
data, addresses, or memory words. Inclusion verification detects regression
relative to the supplied checkpoint while allowing later issue/accept events.
Authenticity and rollback resistance depend on an independently protected
checkpoint custodian; this tool has no trust anchor or signing key.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote

try:
    from .audit_record_capture_provenance import _nonce
    from .audit_record_capture_stream_binding import _digest, _parse, _read_limited
except ImportError:
    from audit_record_capture_provenance import _nonce
    from audit_record_capture_stream_binding import _digest, _parse, _read_limited

SCHEMA = 'wild-arms-ps1-verifier-continuity-checkpoint-v1'
REPORT_SCHEMA = 'wild-arms-ps1-verifier-continuity-audit-v1'
MAX_ROWS = 4096
MAX_CHECKPOINT_BYTES = 640 * 1024
CHALLENGE_FIELDS = ('nonce', 'issued_at', 'expires_at', 'consumed')
ACCEPTED_FIELDS = ('nonce', 'provenance_sha256', 'accepted_at')


def _private_regular_file(path):
    path = Path(path)
    st = path.lstat()
    parent = path.parent.stat()
    if (not stat.S_ISREG(st.st_mode)
            or st.st_uid != os.getuid() or st.st_mode & 0o077
            or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise ValueError('invalid private verifier file')
    return path


def _snapshot_from_connection(con):
    """Inspect the exact SQLite snapshot/transaction the caller already holds."""
    if con.execute('PRAGMA integrity_check').fetchone() != ('ok',):
        raise ValueError('invalid verifier database integrity')
    if con.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ValueError('invalid verifier foreign keys')
    for table, columns in (
            ('challenges', CHALLENGE_FIELDS),
            ('accepted', ACCEPTED_FIELDS),
            ('accepted_streams', ('sha256', 'nonce'))):
        columns_read = {r[1] for r in con.execute(
            'PRAGMA table_info("' + table + '")')}
        if columns_read != set(columns):
            raise ValueError('unexpected verifier table schema')
    challenges = con.execute(
        'SELECT nonce, issued_at, expires_at, consumed'
        ' FROM challenges ORDER BY nonce LIMIT ?', (MAX_ROWS + 1,)).fetchall()
    accepted = con.execute(
        'SELECT nonce, provenance_sha256, accepted_at'
        ' FROM accepted ORDER BY nonce LIMIT ?', (MAX_ROWS + 1,)).fetchall()
    streams = con.execute(
        'SELECT sha256, nonce FROM accepted_streams'
        ' ORDER BY nonce, sha256 LIMIT ?', (2 * MAX_ROWS + 1,)).fetchall()
    if (len(challenges) > MAX_ROWS or len(accepted) > MAX_ROWS
            or len(streams) > 2 * MAX_ROWS):
        raise ValueError('verifier history beyond checkpoint bounds')

    challenge_map = {}
    for nonce, issued, expires, consumed in challenges:
        _nonce(nonce)
        if (type(issued) is not int or type(expires) is not int
                or type(consumed) is not int or issued < 0
                or not issued < expires or consumed not in (0, 1)
                or nonce in challenge_map):
            raise ValueError('invalid verifier challenge history')
        challenge_map[nonce] = (issued, expires, consumed)

    accepted_map = {}
    for nonce, provenance, accepted_at in accepted:
        _nonce(nonce)
        _digest(provenance)
        if (nonce not in challenge_map or nonce in accepted_map
                or challenge_map[nonce][2] != 1
                or type(accepted_at) is not int or accepted_at < 0
                or accepted_at >= challenge_map[nonce][1]):
            raise ValueError('invalid accepted session history')
        accepted_map[nonce] = (provenance, accepted_at)
    if any(consumed == 1 and nonce not in accepted_map
           for nonce, (_, _, consumed) in challenge_map.items()):
        raise ValueError('consumed verifier nonce without acceptance')

    stream_map = {nonce: [] for nonce in accepted_map}
    seen_stream_digests = set()
    for digest, nonce in streams:
        _digest(digest)
        if (nonce not in stream_map or digest in seen_stream_digests):
            raise ValueError('invalid accepted stream history')
        stream_map[nonce].append(digest)
        seen_stream_digests.add(digest)
    if any(len(values) != 2 for values in stream_map.values()):
        raise ValueError('missing accepted stream commitment')

    def commitment(domain, obj):
        raw = json.dumps(obj, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True).encode('ascii')
        return hashlib.sha256(domain + b'\x00' + raw).hexdigest()

    issued = sorted(commitment(b'wild-arms-issue-v1', [
        nonce, issued_at, expires_at])
        for nonce, (issued_at, expires_at, _) in challenge_map.items())
    accepted_commitments = sorted(commitment(b'wild-arms-accept-v1', [
        nonce, accepted_map[nonce][0], accepted_map[nonce][1],
        sorted(stream_map[nonce])])
        for nonce in accepted_map)
    return {'schema': SCHEMA, 'issued_commitments': issued,
            'accepted_commitments': accepted_commitments}


def _read_database(path):
    """Return canonical commitments from one consistent read transaction."""
    path = _private_regular_file(path)
    uri = 'file:' + quote(str(path.absolute()), safe='/') + '?mode=ro'
    try:
        with closing(sqlite3.connect(uri, uri=True, isolation_level=None,
                                     timeout=10)) as con:
            con.execute('PRAGMA busy_timeout=10000')
            con.execute('BEGIN')
            try:
                state = _snapshot_from_connection(con)
                con.commit()
                return state
            except Exception:
                con.rollback()
                raise
    except sqlite3.DatabaseError as exc:
        raise ValueError('invalid verifier database') from exc


def _continuity_flags(current, historical):
    """The historical commitment set must survive in current state."""
    issued_kept = set(historical['issued_commitments']).issubset(
        current['issued_commitments'])
    accepted_kept = set(historical['accepted_commitments']).issubset(
        current['accepted_commitments'])
    return issued_kept, accepted_kept


def _validate_checkpoint(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CHECKPOINT_BYTES:
        raise ValueError('invalid bounded checkpoint')
    checkpoint = _parse(raw)
    if (type(checkpoint) is not dict or set(checkpoint) != {
            'schema', 'issued_commitments', 'accepted_commitments'}
            or checkpoint['schema'] != SCHEMA):
        raise ValueError('invalid checkpoint format')
    for field in ('issued_commitments', 'accepted_commitments'):
        values = checkpoint[field]
        if type(values) is not list or len(values) > MAX_ROWS:
            raise ValueError('invalid checkpoint history')
        for digest in values:
            _digest(digest)
        if values != sorted(set(values)):
            raise ValueError('unsorted or duplicated checkpoint entries')
    if len(checkpoint['accepted_commitments']) > len(checkpoint['issued_commitments']):
        raise ValueError('inconsistent checkpoint counts')
    return checkpoint


def check(db_path, checkpoint_raw):
    """Allow progress but refuse missing or modified older ledger entries."""
    historical = _validate_checkpoint(checkpoint_raw)
    current = _read_database(db_path)
    accepted_kept = set(historical['accepted_commitments']).issubset(
        current['accepted_commitments'])
    issued_kept = set(historical['issued_commitments']).issubset(
        current['issued_commitments'])
    return {
        'schema': REPORT_SCHEMA,
        'checkpoint_format_valid': True,
        'prior_issued_sessions_checked': len(historical['issued_commitments']),
        'prior_accepted_sessions_checked': len(historical['accepted_commitments']),
        'all_prior_issued_sessions_preserved': issued_kept,
        'all_prior_accepted_sessions_preserved': accepted_kept,
        'continuous_relative_to_supplied_checkpoint': bool(issued_kept and accepted_kept),
        'checkpoint_independently_authenticated': False,
        'external_anchor_replay_prevention_guaranteed': False,
        'database_rollback_globally_excluded': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_nonces_or_values_emitted': False,
    }


def _write_new_private(path, raw):
    """Do not replace existing checkpoints; fsync private file and directory."""
    path = Path(path)
    parent = path.parent
    st = parent.stat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise ValueError('checkpoint destination not private')
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        dirfd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def save_checkpoint(db_path, output_path):
    state = _read_database(db_path)
    raw = (json.dumps(state, sort_keys=True, separators=(',', ':'))
           + '\n').encode('ascii')
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError('checkpoint exceeds maximum size')
    _write_new_private(output_path, raw)
    return {
        'schema': REPORT_SCHEMA, 'checkpoint_file_created': True,
        'issued_sessions_committed': len(state['issued_commitments']),
        'accepted_sessions_committed': len(state['accepted_commitments']),
        'checkpoint_independently_authenticated': False,
        'external_anchor_replay_prevention_guaranteed': False,
        'private_hashes_nonces_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    snapshot = sub.add_parser('snapshot', help='write a new private checkpoint file')
    snapshot.add_argument('database', type=Path)
    snapshot.add_argument('private_checkpoint_output', type=Path)
    verify = sub.add_parser('verify', help='check against externally retained checkpoint')
    verify.add_argument('database', type=Path)
    verify.add_argument('trusted_private_checkpoint', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'snapshot':
            report = save_checkpoint(args.database, args.private_checkpoint_output)
        else:
            checkpoint = _read_limited(args.trusted_private_checkpoint,
                                       MAX_CHECKPOINT_BYTES)
            report = check(args.database, checkpoint)
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, sqlite3.Error):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_nonces_or_values_emitted': False},
            sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    if args.mode == 'snapshot':
        return 0
    return 0 if report['continuous_relative_to_supplied_checkpoint'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
