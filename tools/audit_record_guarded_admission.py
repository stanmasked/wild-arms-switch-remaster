"""Opt-in fail-closed admission using a separately retained continuity anchor.

Every guarded issue/accept operation locks the verifier's SQLite database
with BEGIN IMMEDIATE, verifies that the entire historical checkpoint is
contained in the *same transaction's* state, then changes that state.
Only the external custodian can establish authenticity of the checkpoint.
Legacy stage-245 commands remain available and are NOT automatically gated.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3
import time

try:
    from .audit_record_atomic_verifier import (
        _connect, MIN_TTL_SECONDS, MAX_TTL_SECONDS,
    )
    from .audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES,
        MAX_RECEIPT_BYTES,
    )
    from .audit_record_capture_stream_binding import (
        _read_limited, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _validate_checkpoint,
        _snapshot_from_connection, _continuity_flags, MAX_CHECKPOINT_BYTES,
    )
except ImportError:
    from audit_record_atomic_verifier import _connect, MIN_TTL_SECONDS, MAX_TTL_SECONDS
    from audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES,
        MAX_RECEIPT_BYTES,
    )
    from audit_record_capture_stream_binding import (
        _read_limited, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_verifier_checkpoint import (
        _private_regular_file, _validate_checkpoint,
        _snapshot_from_connection, _continuity_flags, MAX_CHECKPOINT_BYTES,
    )

REPORT_SCHEMA = 'wild-arms-ps1-guarded-admission-v1'
ISSUE_SCHEMA = 'wild-arms-ps1-guarded-issue-v1'


class ContinuityRegression(ValueError):
    """The current database lacks a prior independently supplied commitment."""


def _checkpoint(path):
    """Read only a private regular file; never treat a DB-local hash as anchor."""
    return _validate_checkpoint(_read_limited(
        _private_regular_file(path), MAX_CHECKPOINT_BYTES))


def _check_locked(con, historical):
    """Run under BEGIN IMMEDIATE, before any issue/accept mutation."""
    current = _snapshot_from_connection(con)
    issued_kept, accepted_kept = _continuity_flags(current, historical)
    if not (issued_kept and accepted_kept):
        raise ContinuityRegression('trusted checkpoint continuity failure')


def _now(now):
    timestamp = int(time.time() if now is None else now)
    if timestamp < 0:
        raise ValueError('invalid verifier time')
    return timestamp


def issue_guarded(db_path, checkpoint_path, *, ttl_seconds=300, now=None):
    """Return fresh private nonce only after passing the in-transaction gate."""
    if (type(ttl_seconds) is not int
            or not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS):
        raise ValueError('invalid challenge lifetime')
    historical = _checkpoint(checkpoint_path)
    timestamp = _now(now)
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            _check_locked(con, historical)
            nonce = secrets.token_hex(16)
            con.execute(
                'INSERT INTO challenges(nonce, issued_at, expires_at)'
                ' VALUES (?, ?, ?)', (nonce, timestamp, timestamp + ttl_seconds))
            con.commit()
            return nonce
        except Exception:
            con.rollback()
            raise


def accept_guarded(db_path, checkpoint_path, exe, temporal_raw, binding_raw,
                   before_raw, after_raw, provenance_raw, before_receipt_raw,
                   after_receipt_raw, *, now=None):
    """Accept at most once; never spend a nonce on failed evidence or rollback."""
    historical = _checkpoint(checkpoint_path)
    prior = audit_provenance(
        exe, temporal_raw, binding_raw, before_raw, after_raw,
        provenance_raw, before_receipt_raw, after_receipt_raw)
    if not prior['all_supplied_provenance_claims_consistent']:
        return False
    provenance = _json_object(provenance_raw, MAX_PROVENANCE_BYTES)
    nonce = provenance['session_nonce']
    timestamp = _now(now)
    before_hash, after_hash = _sha(before_raw), _sha(after_raw)
    if before_hash == after_hash:
        raise ValueError('identical capture stream digests')
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            _check_locked(con, historical)
            item = con.execute(
                'SELECT issued_at, expires_at, consumed'
                ' FROM challenges WHERE nonce=?', (nonce,)).fetchone()
            if (item is None or item[2] or timestamp < item[0]
                    or timestamp >= item[1]):
                con.rollback()
                return False
            con.execute(
                'INSERT INTO accepted(nonce, provenance_sha256, accepted_at)'
                ' VALUES (?, ?, ?)', (nonce, _sha(provenance_raw), timestamp))
            con.execute('INSERT INTO accepted_streams VALUES (?, ?)',
                        (before_hash, nonce))
            con.execute('INSERT INTO accepted_streams VALUES (?, ?)',
                        (after_hash, nonce))
            n = con.execute(
                'UPDATE challenges SET consumed=1'
                ' WHERE nonce=? AND consumed=0', (nonce,)).rowcount
            if n != 1:
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


def _report(*, accepted=False, issued=False, regression=False):
    return {
        'schema': REPORT_SCHEMA,
        'guarded_issue_committed': bool(issued),
        'guarded_acceptance_committed': bool(accepted),
        'historical_checkpoint_regression_detected': bool(regression),
        'same_transaction_continuity_check_passed': bool(issued or accepted),
        'external_checkpoint_independently_authenticated': False,
        'checkpoint_updated_atomically_with_database': False,
        'unanchored_recent_operations_rollback_protected': False,
        'legacy_verifier_commands_also_guarded': False,
        'original_ps1_execution_verified': False,
        'original_game_record_size_verified': False,
        'native_switch_game_build_verified': False,
        'private_nonces_hashes_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    issue_parser = sub.add_parser('issue')
    issue_parser.add_argument('database', type=Path)
    issue_parser.add_argument('externally_retained_checkpoint', type=Path)
    issue_parser.add_argument('--ttl-seconds', type=int, default=300)
    accept_parser = sub.add_parser('accept')
    accept_parser.add_argument('database', type=Path)
    accept_parser.add_argument('externally_retained_checkpoint', type=Path)
    for name in ('disc', 'inventory', 'temporal_claim', 'binding_manifest',
                 'before_stream', 'after_stream', 'provenance',
                 'before_receipt', 'after_receipt'):
        accept_parser.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'issue':
            nonce = issue_guarded(args.database, args.externally_retained_checkpoint,
                                  ttl_seconds=args.ttl_seconds)
            # Intentionally release nonce only at issue time for PRIVATE
            # delivery to collector; never emit it from acceptance/errors.
            print(json.dumps({
                'schema': ISSUE_SCHEMA, 'session_nonce': nonce,
                'expires_in_seconds': args.ttl_seconds,
                'external_checkpoint_independently_authenticated': False,
            }, sort_keys=True))
            return 0
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        matches = [row for row in entries if type(row) is dict
                   and row.get('path') == '/EXE/WILDARMS.EXE;1'
                   and not row.get('directory', False)]
        if len(matches) != 1:
            raise ValueError('missing original game executable')
        raw = (
            read_raw_iso_entry(args.disc, matches[0]),
            _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
            _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
            _read_limited(args.before_stream, MAX_STREAM_BYTES),
            _read_limited(args.after_stream, MAX_STREAM_BYTES),
            _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
            _read_limited(args.before_receipt, MAX_RECEIPT_BYTES),
            _read_limited(args.after_receipt, MAX_RECEIPT_BYTES),
        )
        accepted = accept_guarded(args.database, args.externally_retained_checkpoint,
                                  *raw)
        print(json.dumps(_report(accepted=accepted), sort_keys=True))
        return 0 if accepted else 1
    except ContinuityRegression:
        print(json.dumps(_report(regression=True), sort_keys=True))
        return 1
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, sqlite3.Error):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_nonces_hashes_or_values_emitted': False,
        }, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
