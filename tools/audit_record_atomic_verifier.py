"""Local, verifier-operated single-use challenge and SQLite acceptance gate.

Only use with a verifier-owned private local database. This does not attest
the PS1, independently authenticate a debugger, or stop a compromised owner
of the database. Validation occurs before a BEGIN IMMEDIATE transaction;
uniqueness and challenge consumption happen atomically in that transaction.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time

try:
    from .audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES,
        MAX_RECEIPT_BYTES,
    )
    from .audit_record_capture_stream_binding import (
        _read_limited, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
except ImportError:
    from audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES,
        MAX_RECEIPT_BYTES,
    )
    from audit_record_capture_stream_binding import (
        _read_limited, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES

REPORT_SCHEMA = 'wild-arms-ps1-atomic-verifier-audit-v1'
ISSUE_SCHEMA = 'wild-arms-ps1-verifier-issued-nonce-v1'
MIN_TTL_SECONDS = 30
MAX_TTL_SECONDS = 3600


def _connect(db_path, *, create=False):
    path = Path(db_path)
    if path.name in ('', '.', '..'):
        raise ValueError('invalid verifier database')
    parent = path.parent
    pst = parent.stat()
    if (not stat.S_ISDIR(pst.st_mode) or pst.st_uid != os.getuid()
            or pst.st_mode & 0o077):
        raise ValueError('verifier directory must be private')
    if create:
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise ValueError('verifier database must be private regular file')
    con = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    con.execute('PRAGMA busy_timeout=10000')
    con.execute('PRAGMA journal_mode=DELETE')
    con.execute('PRAGMA synchronous=FULL')
    return con


def _init_tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS challenges (
        nonce TEXT PRIMARY KEY,
        issued_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0 CHECK (consumed IN (0, 1))
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS accepted (
        nonce TEXT PRIMARY KEY REFERENCES challenges(nonce),
        provenance_sha256 TEXT NOT NULL UNIQUE,
        accepted_at INTEGER NOT NULL
    )""")
    # One digest registry for both roles blocks cross-role reuse as well.
    con.execute("""CREATE TABLE IF NOT EXISTS accepted_streams (
        sha256 TEXT PRIMARY KEY,
        nonce TEXT NOT NULL REFERENCES accepted(nonce)
    )""")


def issue(db_path, *, ttl_seconds=300, now=None):
    """Create a random, verifier-owned one-time challenge. Return nonce.

    The verifier must transmit it privately to the recorder *before* capture;
    it may NOT take a nonce suggested by the recorder.
    """
    if type(ttl_seconds) is not int or not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError('invalid challenge lifetime')
    timestamp = int(time.time() if now is None else now)
    if timestamp < 0:
        raise ValueError('invalid verifier time')
    nonce = secrets.token_hex(16)
    with closing(_connect(db_path, create=True)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            _init_tables(con)
            con.execute(
                'INSERT INTO challenges(nonce, issued_at, expires_at) VALUES (?, ?, ?)',
                (nonce, timestamp, timestamp + ttl_seconds))
            con.commit()
        except Exception:
            con.rollback()
            raise
    return nonce


def accept(db_path, exe, temporal_raw, binding_raw, before_raw, after_raw,
           provenance_raw, before_receipt_raw, after_receipt_raw, *, now=None):
    """Validate evidence and consume a matching unexpired challenge once.

    On validation failure or race loss, do not consume any challenge.
    No export of private hashes, session nonces, or memory values.
    """
    prior = audit_provenance(
        exe, temporal_raw, binding_raw, before_raw, after_raw,
        provenance_raw, before_receipt_raw, after_receipt_raw)
    if not prior['all_supplied_provenance_claims_consistent']:
        return False
    provenance = _json_object(provenance_raw, MAX_PROVENANCE_BYTES)
    nonce = provenance['session_nonce']
    timestamp = int(time.time() if now is None else now)
    if timestamp < 0:
        raise ValueError('invalid verifier time')
    before_digest, after_digest = _sha(before_raw), _sha(after_raw)
    if before_digest == after_digest:
        raise ValueError('identical private capture streams')
    try:
        with closing(_connect(db_path)) as con:
            con.execute('BEGIN IMMEDIATE')
            try:
                entry = con.execute(
                    'SELECT expires_at, consumed FROM challenges WHERE nonce = ?',
                    (nonce,)).fetchone()
                if entry is None or entry[1] or timestamp >= entry[0]:
                    con.rollback()
                    return False
                # The following inserts and single-use marker commit together.
                # Any unique-key collision aborts the entire transaction.
                con.execute(
                    'INSERT INTO accepted(nonce, provenance_sha256, accepted_at)'
                    ' VALUES (?, ?, ?)', (nonce, _sha(provenance_raw), timestamp))
                con.execute('INSERT INTO accepted_streams VALUES (?, ?)',
                            (before_digest, nonce))
                con.execute('INSERT INTO accepted_streams VALUES (?, ?)',
                            (after_digest, nonce))
                updated = con.execute(
                    'UPDATE challenges SET consumed = 1'
                    ' WHERE nonce = ? AND consumed = 0', (nonce,)).rowcount
                if updated != 1:
                    con.rollback()
                    return False
                con.commit()
                return True
            except sqlite3.IntegrityError:
                con.rollback()
                return False
            except Exception:
                con.rollback()
                raise
    except sqlite3.DatabaseError as exc:
        raise ValueError('invalid verifier database') from exc


def _result(accepted):
    return {
        'schema': REPORT_SCHEMA, 'accepted_once': bool(accepted),
        'verifier_issued_nonce_registry_used': True,
        'atomic_local_acceptance_transaction': bool(accepted),
        'trusted_hardware_attestation_verified': False,
        'debugger_origin_independently_authenticated': False,
        'external_database_integrity_attested': False,
        'original_ps1_execution_verified': False,
        'original_game_record_size_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_addresses_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    issue_parser = sub.add_parser('issue', help='generate and privately store a nonce')
    issue_parser.add_argument('database', type=Path)
    issue_parser.add_argument('--ttl-seconds', type=int, default=300)
    accept_parser = sub.add_parser('accept', help='validate and consume nonce once')
    accept_parser.add_argument('database', type=Path)
    for name in ('disc', 'inventory', 'temporal_claim', 'binding_manifest',
                 'before_stream', 'after_stream', 'provenance',
                 'before_receipt', 'after_receipt'):
        accept_parser.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'issue':
            nonce = issue(args.database, ttl_seconds=args.ttl_seconds)
            # The nonce is intentionally released ONLY by this issuance command,
            # for private delivery to the recorder, never by acceptance reports.
            print(json.dumps({'schema': ISSUE_SCHEMA,
                              'session_nonce': nonce,
                              'expires_in_seconds': args.ttl_seconds}, sort_keys=True))
            return 0
        inventory = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        found = [row for row in inventory if type(row) is dict
                 and row.get('path') == '/EXE/WILDARMS.EXE;1'
                 and not row.get('directory', False)]
        if len(found) != 1:
            raise ValueError('missing original EXE entry')
        data = (
            read_raw_iso_entry(args.disc, found[0]),
            _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
            _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
            _read_limited(args.before_stream, MAX_STREAM_BYTES),
            _read_limited(args.after_stream, MAX_STREAM_BYTES),
            _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
            _read_limited(args.before_receipt, MAX_RECEIPT_BYTES),
            _read_limited(args.after_receipt, MAX_RECEIPT_BYTES),
        )
        accepted = accept(args.database, *data)
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, sqlite3.Error):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_addresses_or_values_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(_result(accepted), sort_keys=True))
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
