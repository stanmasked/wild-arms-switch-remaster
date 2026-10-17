"""Exclusive, durable, non-expiring witness head fence for custody writes.

A separately administered witness offers one in-flight fenced custody
operation at a time. A claim is conditional on the exact witness head
and a SHA-256 commitment of a specific authenticated custody request.
Witness recovery records cannot advance while fenced. Release requires
the same token and request digest. Retained fences survive power loss:
an interrupted operation must be reconciled; no unsafe timed expiry.
"""
import hashlib
import re
from contextlib import closing

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_anchor_handoff import GENESIS
    from .audit_record_capture_stream_binding import _digest
    from .audit_record_recovery_witness import _witness_rows
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import GENESIS
    from audit_record_capture_stream_binding import _digest
    from audit_record_recovery_witness import _witness_rows

TOKEN_RE = re.compile(r'[0-9a-f]{32}\Z')
COLUMNS = {'slot', 'owner_sha256', 'custody_request_sha256',
           'recovery_count', 'witness_chain_sha256'}
DOMAIN = b'wild-arms-ps1-witness-custody-fence-owner-v1\x00'


class FenceConflict(ValueError):
    """Independent witness cannot authorize a conflicting custody writer."""


def _owner(token):
    if type(token) is not str or not TOKEN_RE.fullmatch(token):
        raise ValueError('invalid private fence token')
    return hashlib.sha256(DOMAIN + bytes.fromhex(token)).hexdigest()


def _fence_row(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS recovery_witness_fence (
            slot INTEGER PRIMARY KEY CHECK(slot=1),
            owner_sha256 TEXT NOT NULL,
            custody_request_sha256 TEXT NOT NULL,
            recovery_count INTEGER NOT NULL CHECK(recovery_count>=0),
            witness_chain_sha256 TEXT NOT NULL
        )""")
    elif con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                     "AND name='recovery_witness_fence'").fetchone() is None:
        return None
    columns = {r[1] for r in con.execute(
        'PRAGMA table_info("recovery_witness_fence")')}
    if columns != COLUMNS:
        raise ValueError('invalid private witness fence schema')
    rows = con.execute(
        'SELECT slot,owner_sha256,custody_request_sha256,'
        'recovery_count,witness_chain_sha256 FROM recovery_witness_fence'
    ).fetchall()
    if len(rows) > 1:
        raise ValueError('invalid fence row count')
    if not rows:
        return None
    row = rows[0]
    if row[0] != 1 or type(row[3]) is not int or row[3] < 0:
        raise ValueError('invalid private witness fence row')
    for field in (row[1], row[2], row[4]):
        _digest(field)
    return row


def require_unfenced(con):
    """Called in the SAME writer transaction as an appended recovery event."""
    if _fence_row(con) is not None:
        raise FenceConflict('independent witness recovery head is fenced')


def claim(db, token, request_digest, expected_count, expected_chain):
    """Atomic exact-head CAS, idempotent only for an identical request."""
    owner = _owner(token)
    _digest(request_digest)
    _digest(expected_chain)
    if type(expected_count) is not int or expected_count < 0:
        raise ValueError('invalid expected independent witness version')
    with closing(_connect(db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            try:
                from .audit_record_witness_fence_reconciliation import _audit
            except ImportError:
                from audit_record_witness_fence_reconciliation import _audit
            _audit(con)
            rows = _witness_rows(con)
            count = len(rows)
            chain = rows[-1][4] if rows else GENESIS
            if (count, chain) != (expected_count, expected_chain):
                raise FenceConflict('independent witness head changed')
            previous = _fence_row(con, create=True)
            requested = (owner, request_digest, expected_count, expected_chain)
            if previous is not None:
                if previous[1:] != requested:
                    raise FenceConflict('another custody writer owns witness fence')
                con.commit()
                return False
            con.execute(
                'INSERT INTO recovery_witness_fence'
                ' (slot,owner_sha256,custody_request_sha256,'
                ' recovery_count,witness_chain_sha256)'
                ' VALUES(1,?,?,?,?)', requested)
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise


def release(db, token, request_digest):
    """Release exactly the previously claimed fence after custody attempt."""
    owner = _owner(token)
    _digest(request_digest)
    with closing(_connect(db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            try:
                from .audit_record_witness_fence_reconciliation import _audit
            except ImportError:
                from audit_record_witness_fence_reconciliation import _audit
            _audit(con)
            _witness_rows(con)
            current = _fence_row(con)
            if current is None:
                # A lost response after successful release can be retried.
                con.commit()
                return False
            if current[1] != owner or current[2] != request_digest:
                raise FenceConflict('different custody request owns witness fence')
            con.execute('DELETE FROM recovery_witness_fence WHERE slot=1')
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise
