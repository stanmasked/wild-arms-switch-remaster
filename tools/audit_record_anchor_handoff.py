"""Verifier-to-custodian private checkpoint handoff with durable receipt recovery.

This is a *local reference implementation* of the custodian side. Its
security relies on an independent operator and independently protected
custodian DB; it cannot authenticate custody from untrusted client inputs
or provide atomicity across the two databases.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_capture_stream_binding import _sha, _digest, _read_limited, _parse
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _validate_checkpoint, _write_new_private,
        save_checkpoint, MAX_CHECKPOINT_BYTES,
    )
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_capture_stream_binding import _sha, _digest, _read_limited, _parse
    from audit_record_verifier_checkpoint import (
        _private_regular_file, _validate_checkpoint, _write_new_private,
        save_checkpoint, MAX_CHECKPOINT_BYTES,
    )

RECEIPT_SCHEMA = 'wild-arms-ps1-custodian-handoff-receipt-v1'
REPORT_SCHEMA = 'wild-arms-ps1-custodian-handoff-audit-v1'
MAX_ROUNDS = 256
MAX_RECEIPT_BYTES = 1024
GENESIS = '0' * 64


class HandoffRegression(ValueError):
    """Receipt/anchor continuity refuses a stale submitted checkpoint."""


def _canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True) + '\n').encode('ascii')


def _receipt(seq, checkpoint_sha256, previous):
    return {
        'schema': RECEIPT_SCHEMA,
        'sequence': seq,
        'checkpoint_sha256': checkpoint_sha256,
        'previous_receipt_sha256': previous,
    }


def _receipt_hash(receipt):
    return hashlib.sha256(b'wild-arms-custodian-receipt-v1\x00'
                          + _canonical(receipt)).hexdigest()


def _history(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS anchor_history (
            sequence INTEGER PRIMARY KEY,
            checkpoint_sha256 TEXT NOT NULL UNIQUE,
            previous_receipt_sha256 TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL UNIQUE,
            checkpoint_bytes BLOB NOT NULL
        )""")
    elif con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='anchor_history'").fetchone() is None:
        raise ValueError('no committed custodian history')
    columns = {row[1] for row in con.execute(
        'PRAGMA table_info("anchor_history")')}
    if columns != {'sequence', 'checkpoint_sha256',
                   'previous_receipt_sha256', 'receipt_sha256',
                   'checkpoint_bytes'}:
        raise ValueError('invalid custodian table schema')
    entries = con.execute(
        'SELECT sequence, checkpoint_sha256, previous_receipt_sha256,'
        ' receipt_sha256, checkpoint_bytes FROM anchor_history'
        ' ORDER BY sequence LIMIT ?', (MAX_ROUNDS + 1,)).fetchall()
    if len(entries) > MAX_ROUNDS:
        raise ValueError('custodian history exceeds bounds')
    previous = GENESIS
    last_checkpoint = None
    for index, (seq, digest, linked, receipt_digest, blob) in enumerate(entries, 1):
        if (type(seq) is not int or seq != index
                or type(blob) is not bytes
                or type(linked) is not str or linked != previous):
            raise ValueError('invalid custodian sequence')
        _digest(digest)
        _digest(receipt_digest)
        if len(blob) > MAX_CHECKPOINT_BYTES or _sha(blob) != digest:
            raise ValueError('corrupted private custodian checkpoint')
        checkpoint = _validate_checkpoint(blob)
        if last_checkpoint is not None:
            for field in ('issued_commitments', 'accepted_commitments'):
                if not set(last_checkpoint[field]).issubset(checkpoint[field]):
                    raise ValueError('regressed custodian history')
        receipt = _receipt(seq, digest, linked)
        if _receipt_hash(receipt) != receipt_digest:
            raise ValueError('invalid private custodian receipt chain')
        previous, last_checkpoint = receipt_digest, checkpoint
    return entries


def deposit(custodian_db, checkpoint_raw, *, expected_sequence=None,
            expected_receipt_sha256=None, reservation_token=None,
            witness_head=None):
    """Durably store next monotonic checkpoint, no output receipt side effect.

    A repeat of the *latest* deposit is idempotent; an older checkpoint
    cannot be replayed after a newer one has been accepted.

    With expected_sequence + expected_receipt_sha256 this becomes an
    atomic single-winner CAS inside BEGIN IMMEDIATE. Only an *exact*
    retry of the immediate next committed round is idempotent.
    """
    candidate = _validate_checkpoint(checkpoint_raw)
    digest = _sha(checkpoint_raw)
    conditional = (expected_sequence is not None or
                   expected_receipt_sha256 is not None)
    if reservation_token is not None and not conditional:
        raise ValueError('reserved deposit requires expected custody head')
    if conditional:
        if (type(expected_sequence) is not int or expected_sequence < 1
                or type(expected_receipt_sha256) is not str):
            raise ValueError('invalid expected custodian head')
        _digest(expected_receipt_sha256)
    with closing(_connect(custodian_db, create=True)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            try:
                from .audit_record_custodian_write_quarantine import require_unquarantined
            except ImportError:
                from audit_record_custodian_write_quarantine import require_unquarantined
            require_unquarantined(con)
            if witness_head is not None:
                try:
                    from .audit_record_recovery_witness import check_locked
                except ImportError:
                    from audit_record_recovery_witness import check_locked
                check_locked(con, witness_head, require_exact=True)
            prior = _history(con, create=True)
            try:
                from .audit_record_custodian_reservation import (
                    reservation_row, token_hash, ReservationConflict,
                )
            except ImportError:
                from audit_record_custodian_reservation import (
                    reservation_row, token_hash, ReservationConflict,
                )
            from .audit_record_custodian_recovery import audit_history
            audit_history(con)
            recovered_before = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table'"
                " AND name='custodian_recovery_history'").fetchone() is not None
            reserved = reservation_row(con)
            if reservation_token is not None:
                offered_token_hash = token_hash(reservation_token)
                if reserved is None:
                    raise ReservationConflict('required reservation missing')
            else:
                offered_token_hash = None
                # Once a custodian enables durable reservations, block
                # legacy/unreserved writes permanently, including after
                # the previous reservation was committed. Otherwise an
                # older client could silently bypass the active policy.
                if reserved is not None or recovered_before:
                    raise ReservationConflict('custodian requires reserved deposits')
            if conditional:
                if not prior:
                    raise HandoffRegression('expected custodian history absent')
                head = prior[-1]
                matches_expected = (head[0] == expected_sequence and
                                    head[3] == expected_receipt_sha256)
                retry_of_exact_next = (
                    head[0] == expected_sequence + 1
                    and head[2] == expected_receipt_sha256
                    and head[1] == digest)
                if retry_of_exact_next:
                    if reservation_token is not None:
                        if (reserved is None or reserved[4] != 'committed'
                                or (reserved[1], reserved[2], reserved[3],
                                    reserved[5]) != (
                                        expected_sequence, expected_receipt_sha256,
                                        offered_token_hash, digest)):
                            raise ReservationConflict('reserved replay does not match owner')
                    con.commit()
                    return head[0], False
                if not matches_expected:
                    raise HandoffRegression('stale expected custodian history')
                if reservation_token is not None and (
                        reserved is None or reserved[4] != 'reserved'
                        or (reserved[1], reserved[2], reserved[3]) != (
                            expected_sequence, expected_receipt_sha256,
                            offered_token_hash)):
                    raise ReservationConflict('different or unowned custody reservation')
            if prior and prior[-1][1] == digest:
                if conditional:
                    raise HandoffRegression('candidate does not advance custody head')
                con.commit()
                return prior[-1][0], False
            if len(prior) >= MAX_ROUNDS:
                raise ValueError('custodian sequence capacity exceeded')
            if prior:
                latest = _validate_checkpoint(prior[-1][4])
                for field in ('issued_commitments', 'accepted_commitments'):
                    if not set(latest[field]).issubset(candidate[field]):
                        raise HandoffRegression('checkpoint is older than custodian state')
                if (len(latest['issued_commitments'])
                        == len(candidate['issued_commitments'])
                        and len(latest['accepted_commitments'])
                        == len(candidate['accepted_commitments'])):
                    raise HandoffRegression('duplicate checkpoint state')
            seq = len(prior) + 1
            previous = prior[-1][3] if prior else GENESIS
            receipt_hash = _receipt_hash(_receipt(seq, digest, previous))
            con.execute(
                'INSERT INTO anchor_history'
                '(sequence,checkpoint_sha256,previous_receipt_sha256,'
                ' receipt_sha256,checkpoint_bytes) VALUES(?,?,?,?,?)',
                (seq, digest, previous, receipt_hash, checkpoint_raw))
            if reservation_token is not None:
                con.execute(
                    "UPDATE custodian_reservation SET status='committed',"
                    "committed_checkpoint_sha256=? WHERE slot=1",
                    (digest,))
            con.commit()
            return seq, True
        except Exception:
            con.rollback()
            raise


def _read_latest(custodian_db):
    with closing(_connect(custodian_db)) as con:
        con.execute('BEGIN')
        try:
            entries = _history(con)
            if not entries:
                raise ValueError('no committed private custodian checkpoint')
            con.commit()
            return entries[-1]
        except Exception:
            con.rollback()
            raise


def deliver_receipt(custodian_db, private_output):
    """Recover/reissue a private receipt after any post-deposit crash."""
    latest = _read_latest(custodian_db)
    value = _receipt(latest[0], latest[1], latest[2])
    _write_new_private(private_output, _canonical(value))
    return latest[0]


def export_latest(custodian_db, private_output):
    """Export the last *committed* checkpoint for stage-247 guard input."""
    latest = _read_latest(custodian_db)
    _write_new_private(private_output, latest[4])
    return latest[0]


def verify_receipt(custodian_db, receipt_raw):
    """Verify supplied *private* receipt against custodian's local state."""
    if type(receipt_raw) is not bytes or not 0 < len(receipt_raw) <= MAX_RECEIPT_BYTES:
        raise ValueError('invalid bounded private receipt')
    obj = _parse(receipt_raw)
    if (type(obj) is not dict
            or set(obj) != {'schema', 'sequence', 'checkpoint_sha256',
                           'previous_receipt_sha256'}
            or obj['schema'] != RECEIPT_SCHEMA
            or type(obj['sequence']) is not int or obj['sequence'] < 1):
        raise ValueError('invalid private custodian receipt schema')
    _digest(obj['checkpoint_sha256'])
    _digest(obj['previous_receipt_sha256'])
    entry = _read_latest(custodian_db)
    return obj == _receipt(entry[0], entry[1], entry[2])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('verifier_database', type=Path)
    prepare.add_argument('private_checkpoint_output', type=Path)
    deposit_cmd = sub.add_parser('deposit')
    deposit_cmd.add_argument('custodian_database', type=Path)
    deposit_cmd.add_argument('private_checkpoint_offer', type=Path)
    for name in ('receipt', 'export'):
        p = sub.add_parser(name)
        p.add_argument('custodian_database', type=Path)
        p.add_argument('private_output', type=Path)
    verify = sub.add_parser('verify')
    verify.add_argument('custodian_database', type=Path)
    verify.add_argument('private_receipt', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'prepare':
            saved = save_checkpoint(args.verifier_database,
                                    args.private_checkpoint_output)
            report = {
                'schema': REPORT_SCHEMA, 'private_checkpoint_prepared': True,
                'issued_sessions_checked': saved['issued_sessions_committed'],
                'accepted_sessions_checked': saved['accepted_sessions_committed'],
            }
            code = 0
        elif args.mode == 'deposit':
            raw = _read_limited(_private_regular_file(args.private_checkpoint_offer),
                                MAX_CHECKPOINT_BYTES)
            seq, new = deposit(args.custodian_database, raw)
            report = {'schema': REPORT_SCHEMA,
                      'custodian_commit_recorded': True,
                      'idempotent_latest_deposit': not new,
                      'custodian_sequence': seq}
            code = 0
        elif args.mode == 'receipt':
            seq = deliver_receipt(args.custodian_database, args.private_output)
            report = {'schema': REPORT_SCHEMA,
                      'private_receipt_created': True, 'custodian_sequence': seq}
            code = 0
        elif args.mode == 'export':
            seq = export_latest(args.custodian_database, args.private_output)
            report = {'schema': REPORT_SCHEMA,
                      'private_checkpoint_exported': True, 'custodian_sequence': seq}
            code = 0
        else:
            valid = verify_receipt(
                args.custodian_database,
                _read_limited(_private_regular_file(args.private_receipt),
                              MAX_RECEIPT_BYTES))
            report = {'schema': REPORT_SCHEMA, 'latest_receipt_matches_custodian': valid}
            code = 0 if valid else 1
    except HandoffRegression:
        report = {'schema': REPORT_SCHEMA, 'custodian_handoff_regression_detected': True}
        code = 1
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, sqlite3.Error):
        report = {'schema': REPORT_SCHEMA, 'valid_input': False,
                  'error_code': 'invalid_private_input'}
        code = 2
    report.update({
        'independent_custodian_authentication_performed': False,
        'cross_database_atomic_commit_guaranteed': False,
        'custodian_database_rollback_globally_excluded': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_nonces_or_values_emitted': False,
    })
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
