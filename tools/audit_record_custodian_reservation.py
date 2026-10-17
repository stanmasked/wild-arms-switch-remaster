"""Durable pre-issue reservation of a custodian history head.

A verifier generates and durably retains a random 128-bit reservation token
*before* sending it over mutually authenticated TLS. The custodian stores
only a domain-separated hash of that token under BEGIN IMMEDIATE. Exactly
one uncompleted reservation may own the current custody head. No lease
expiry: recovery needs the same retained token, and abandonment requires
a separately trusted administrative reconciliation not provided here.
"""
from contextlib import closing
import hashlib
import re

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_anchor_handoff import _history, HandoffRegression
    from .audit_record_capture_stream_binding import _digest
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import _history, HandoffRegression
    from audit_record_capture_stream_binding import _digest

TOKEN_PATTERN = re.compile(r'[0-9a-f]{32}\Z')
RESERVATION_COLUMNS = {
    'slot', 'base_sequence', 'base_receipt_sha256', 'token_sha256',
    'status', 'committed_checkpoint_sha256',
}


class ReservationConflict(HandoffRegression):
    """Another verifier has already reserved the custody head."""


def token_hash(token):
    if type(token) is not str or not TOKEN_PATTERN.fullmatch(token):
        raise ValueError('invalid private reservation token')
    return hashlib.sha256(
        b'wild-arms-custodian-reservation-token-v1\x00'
        + bytes.fromhex(token)).hexdigest()


def reservation_row(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS custodian_reservation (
            slot INTEGER PRIMARY KEY CHECK(slot=1),
            base_sequence INTEGER NOT NULL,
            base_receipt_sha256 TEXT NOT NULL,
            token_sha256 TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN('reserved','committed')),
            committed_checkpoint_sha256 TEXT,
            CHECK ((status='reserved' AND committed_checkpoint_sha256 IS NULL)
                OR (status='committed' AND committed_checkpoint_sha256 IS NOT NULL))
        )""")
    elif con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table'"
        " AND name='custodian_reservation'").fetchone() is None:
        return None
    cols = {v[1] for v in con.execute(
        'PRAGMA table_info("custodian_reservation")')}
    if cols != RESERVATION_COLUMNS:
        raise ValueError('invalid custodian reservation schema')
    rows = con.execute(
        'SELECT slot,base_sequence,base_receipt_sha256,token_sha256,'
        'status,committed_checkpoint_sha256 FROM custodian_reservation'
    ).fetchall()
    if len(rows) > 1:
        raise ValueError('invalid custody reservation row count')
    if not rows:
        return None
    row = rows[0]
    if (row[0] != 1 or type(row[1]) is not int or row[1] < 1
            or row[4] not in ('reserved', 'committed')):
        raise ValueError('invalid custody reservation state')
    _digest(row[2])
    _digest(row[3])
    if row[4] == 'committed':
        _digest(row[5])
    elif row[5] is not None:
        raise ValueError('invalid uncommitted reservation')
    return row


def reserve(db, expected_sequence, expected_receipt_sha256, token, *,
            witness_head=None):
    """Idempotently reserve exactly the caller's current custody head."""
    if type(expected_sequence) is not int or expected_sequence < 1:
        raise ValueError('invalid expected reservation version')
    _digest(expected_receipt_sha256)
    thash = token_hash(token)
    with closing(_connect(db, create=True)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            if witness_head is not None:
                try:
                    from .audit_record_recovery_witness import check_locked
                except ImportError:
                    from audit_record_recovery_witness import check_locked
                check_locked(con, witness_head, require_exact=True)
            from .audit_record_custodian_recovery import audit_history
            audit_history(con)
            history = _history(con)
            if not history or (history[-1][0], history[-1][3]) != (
                    expected_sequence, expected_receipt_sha256):
                raise ReservationConflict('custody head changed before reservation')
            prior = reservation_row(con, create=True)
            if prior is not None:
                if prior[4] == 'reserved':
                    if (prior[1], prior[2], prior[3]) == (
                            expected_sequence, expected_receipt_sha256, thash):
                        con.commit()
                        return False
                    raise ReservationConflict('custody head already reserved')
                if prior[1] + 1 != expected_sequence:
                    raise ValueError('committed reservation history mismatch')
            con.execute(
                'INSERT INTO custodian_reservation '
                '(slot,base_sequence,base_receipt_sha256,token_sha256,status)'
                " VALUES(1,?,?,?,'reserved') "
                'ON CONFLICT(slot) DO UPDATE SET '
                'base_sequence=excluded.base_sequence,'
                'base_receipt_sha256=excluded.base_receipt_sha256,'
                'token_sha256=excluded.token_sha256,'
                "status='reserved', committed_checkpoint_sha256=NULL",
                (expected_sequence, expected_receipt_sha256, thash))
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise
