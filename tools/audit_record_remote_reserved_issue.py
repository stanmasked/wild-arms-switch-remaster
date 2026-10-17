"""Opt-in remotely reserved challenge issuance with durable local intent.

A client saves its reservation token and expected signed custody head in its
own verifier SQLite BEFORE contacting the stage-254 mutual TLS custodian.
After reservation acknowledgment it atomically issues one challenge through
stage-249's BEGIN IMMEDIATE transaction, which writes a pending checkpoint.
Remote acknowledgment deposits using the same durable owner token.

Lost remote reserve replies are retried using the same token. A lost local
issue response cannot be replayed to disclose its original nonce: the
pending marker prevents issuing another challenge. No lease expiry or
unverified abandonment; operator reconciliation remains out of scope.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3
import ssl

try:
    from .audit_record_atomic_verifier import _connect, MIN_TTL_SECONDS, MAX_TTL_SECONDS
    from .audit_record_capture_stream_binding import _digest
    from .audit_record_custodian_reservation import token_hash
    from .audit_record_receipt_gated_admission import (
        _ready, _guard, _checkpoint_digest, issue_with_latest,
        acknowledge_with_latest, PendingHandoff, AnchorConflict,
    )
    from .audit_record_remote_admission import _remote_head, _transport
    from .audit_record_verifier_checkpoint import _snapshot_from_connection
    from .audit_record_anchor_handoff import _canonical
except ImportError:
    from audit_record_atomic_verifier import _connect, MIN_TTL_SECONDS, MAX_TTL_SECONDS
    from audit_record_capture_stream_binding import _digest
    from audit_record_custodian_reservation import token_hash
    from audit_record_receipt_gated_admission import (
        _ready, _guard, _checkpoint_digest, issue_with_latest,
        acknowledge_with_latest, PendingHandoff, AnchorConflict,
    )
    from audit_record_remote_admission import _remote_head, _transport
    from audit_record_verifier_checkpoint import _snapshot_from_connection
    from audit_record_anchor_handoff import _canonical

REPORT_SCHEMA = 'wild-arms-ps1-reserved-remote-issue-v1'
INTENT_COLUMNS = {
    'slot', 'base_sequence', 'base_receipt_sha256', 'reservation_token',
}


def _intent(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS remote_issue_reservation (
            slot INTEGER PRIMARY KEY CHECK(slot=1),
            base_sequence INTEGER NOT NULL,
            base_receipt_sha256 TEXT NOT NULL,
            reservation_token TEXT NOT NULL
        )""")
    elif con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table'"
        " AND name='remote_issue_reservation'").fetchone() is None:
        return None
    cols = {r[1] for r in con.execute('PRAGMA table_info(remote_issue_reservation)')}
    if cols != INTENT_COLUMNS:
        raise ValueError('invalid local reservation schema')
    rows = con.execute(
        'SELECT slot,base_sequence,base_receipt_sha256,reservation_token'
        ' FROM remote_issue_reservation').fetchall()
    if len(rows) > 1:
        raise ValueError('invalid local reservation row count')
    if not rows:
        return None
    row = rows[0]
    if row[0] != 1 or type(row[1]) is not int or row[1] < 1:
        raise ValueError('invalid local reservation counter')
    _digest(row[2])
    token_hash(row[3])
    return row


def _prepare(db_path, latest):
    """Create a recoverable pending reservation identity before any network I/O."""
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            _ready(con, latest)
            previous = _intent(con, create=True)
            if previous is not None and (
                    previous[1] == latest[0]
                    and previous[2] == latest[3]):
                con.commit()
                return previous[3]
            if previous is not None and previous[1] >= latest[0]:
                raise AnchorConflict('local reservation conflicts with custody head')
            # Only a previously completed and acknowledged reservation may
            # be replaced; _ready assures the local verifier has no pending
            # checkpoint and is exactly at this independently signed head.
            if previous is not None and previous[1] + 1 != latest[0]:
                raise AnchorConflict('unreconciled local reservation history')
            token = secrets.token_hex(16)
            con.execute(
                'INSERT INTO remote_issue_reservation'
                ' (slot,base_sequence,base_receipt_sha256,reservation_token)'
                ' VALUES(1,?,?,?)'
                ' ON CONFLICT(slot) DO UPDATE SET'
                ' base_sequence=excluded.base_sequence,'
                ' base_receipt_sha256=excluded.base_receipt_sha256,'
                ' reservation_token=excluded.reservation_token',
                (latest[0], latest[3], token))
            con.commit()
            return token
        except Exception:
            con.rollback()
            raise


def issue_reserved(db_path, transport, public_key, pinned_sha256, *, tag,
                   ttl_seconds=300, now=None):
    """Reserve remote custody first; only then issue an actual private nonce."""
    if (type(ttl_seconds) is not int
            or not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS):
        raise ValueError('invalid lifetime, reservation not attempted')
    latest = _remote_head(transport, public_key, pinned_sha256, tag=tag)
    token = _prepare(db_path, latest)
    confirmed = _remote_head(
        transport, public_key, pinned_sha256, tag=tag, action='reserve',
        expected_sequence=latest[0], expected_receipt_sha256=latest[3],
        reservation_token=token)
    if (confirmed[0] != latest[0] or confirmed[3] != latest[3]
            or confirmed[1] != latest[1]):
        raise AnchorConflict('reservation acknowledgment changed custody head')
    return issue_with_latest(
        db_path, latest, ttl_seconds=ttl_seconds, now=now)


def _pending_offer(db_path):
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN')
        try:
            seq, prior_receipt, pending_seq, pending_hash = _guard(con)
            if pending_seq is None:
                con.commit()
                return None
            intent = _intent(con)
            if intent is None or (intent[1], intent[2]) != (
                    seq, prior_receipt):
                raise AnchorConflict('pending operation lacks owning reservation')
            raw = _canonical(_snapshot_from_connection(con))
            if (pending_seq != seq + 1 or
                    _checkpoint_digest(con) != pending_hash):
                raise AnchorConflict('pending checkpoint changed')
            con.commit()
            return raw, seq, prior_receipt, intent[3]
        except Exception:
            con.rollback()
            raise


def acknowledge_reserved(db_path, transport, public_key, pinned_sha256, *, tag):
    """The exact previous reservation token authorizes its custody deposit."""
    pending = _pending_offer(db_path)
    latest = _remote_head(
        transport, public_key, pinned_sha256, tag=tag,
        action='deposit-reserved' if pending is not None else 'latest',
        checkpoint_raw=pending[0] if pending is not None else None,
        expected_sequence=pending[1] if pending is not None else None,
        expected_receipt_sha256=pending[2] if pending is not None else None,
        reservation_token=pending[3] if pending is not None else None)
    return acknowledge_with_latest(db_path, latest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('issue', 'ack'):
        p = sub.add_parser(name)
        p.add_argument('verifier_database', type=Path)
        p.add_argument('host')
        p.add_argument('port', type=int)
        p.add_argument('tls_hostname')
        p.add_argument('tls_client_cert', type=Path)
        p.add_argument('tls_client_key', type=Path)
        p.add_argument('trusted_server_ca', type=Path)
        p.add_argument('server_leaf_der_sha256')
        p.add_argument('pinned_custodian_ed25519_public_key', type=Path)
        p.add_argument('custodian_ed25519_public_pem_sha256')
        p.add_argument('--custodian-tag', required=True)
        if name == 'issue':
            p.add_argument('--ttl-seconds', type=int, default=300)
    args = parser.parse_args(argv)
    try:
        transport = _transport(args)
        if args.mode == 'issue':
            nonce = issue_reserved(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256,
                tag=args.custodian_tag, ttl_seconds=args.ttl_seconds)
            print(json.dumps({
                'schema': REPORT_SCHEMA,
                'private_newly_issued_nonce': nonce,
                'reserved_custodian_acknowledgment_pending': True,
                'existing_nonces_tokens_or_hashes_exposed': False,
            }, sort_keys=True))
            return 0
        accepted = acknowledge_reserved(
            args.verifier_database, transport,
            args.pinned_custodian_ed25519_public_key,
            args.custodian_ed25519_public_pem_sha256, tag=args.custodian_tag)
        code, outcome = 0, {
            'reserved_custodian_acknowledgment_recorded': accepted,
            'already_acknowledged': not accepted,
        }
    except (PendingHandoff, AnchorConflict):
        code, outcome = 1, {'reservation_or_admission_blocked': True}
    except (OSError, ValueError, TypeError, KeyError, RecursionError,
            OverflowError, ssl.SSLError, sqlite3.Error):
        code, outcome = 2, {'valid_input': False,
                            'error_code': 'invalid_private_input_or_reservation'}
    outcome.update({
        'schema': REPORT_SCHEMA,
        'mutually_authenticated_remote_reservation_used': code == 0,
        'local_custodian_db_required': False,
        'independent_remote_deployment_proven': False,
        'legacy_issue_and_deposit_interfaces_fully_gated': False,
        'reservation_abandonment_and_expiry_automated': False,
        'cross_database_atomic_commit_guaranteed': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'existing_nonces_tokens_or_hashes_exposed': False,
    })
    print(json.dumps(outcome, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
