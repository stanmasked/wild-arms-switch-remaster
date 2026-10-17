"""Independent append-only recovery witness and pinned Ed25519 confirmation.

A separately controlled witness retains exact stage-256 recovery events in
its own private SQLite store, never trusting a custodian-supplied replacement
of earlier events. After commit the witness may sign its current head.
The verifier checks the signature and independent high-water watermark
against the custodian's *current* journal, detecting rollback and fork.

This is a reference offline protocol: independent custody and enrollment
are operational preconditions, not automatically provided by this module.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_anchor_handoff import _canonical, _history, GENESIS
    from .audit_record_custodian_recovery import (
        audit_history, _event_hash, EVENT_SCHEMA, MAX_EVENTS,
    )
    from .audit_record_capture_stream_binding import (
        _sha, _digest, _parse, _read_limited,
    )
    from .audit_record_signed_custodian import (
        _openssl, _tag, MAX_PEM_BYTES,
    )
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _write_new_private,
    )
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import _canonical, _history, GENESIS
    from audit_record_custodian_recovery import (
        audit_history, _event_hash, EVENT_SCHEMA, MAX_EVENTS,
    )
    from audit_record_capture_stream_binding import _sha, _digest, _parse, _read_limited
    from audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from audit_record_verifier_checkpoint import _private_regular_file, _write_new_private

SNAPSHOT_SCHEMA = 'wild-arms-ps1-recovery-witness-snapshot-v1'
RECEIPT_SCHEMA = 'wild-arms-ps1-recovery-witness-receipt-v1'
ENVELOPE_SCHEMA = 'wild-arms-ps1-recovery-witness-signed-receipt-v1'
REPORT_SCHEMA = 'wild-arms-ps1-recovery-witness-audit-v1'
WITNESS_DOMAIN = b'wild-arms-ps1-recovery-witness-chain-v1\x00'
SIGN_DOMAIN = b'wild-arms-ps1-recovery-witness-signature-v1\x00'
MAX_SNAPSHOT_BYTES = 512 * 1024
MAX_SIGNED_BYTES = 2048
_HEXSIG = re.compile(r'[0-9a-f]{128}\Z')
_EVENT_COLS = {'sequence', 'request_sha256', 'base_sequence',
               'base_receipt_sha256', 'retired_token_sha256',
               'previous_event_sha256', 'event_sha256'}


class WitnessRegression(ValueError):
    """Cannot forget or replace a previously witnessed recovery event."""


def _event_from_row(row):
    seq, req_hash, base_seq, base_hash, token_hash, previous, digest = row
    return {
        'sequence': seq, 'request_sha256': req_hash,
        'base_sequence': base_seq, 'base_receipt_sha256': base_hash,
        'retired_token_sha256': token_hash,
        'previous_event_sha256': previous, 'event_sha256': digest,
    }


def _validate_events(events, *, require_nonempty=True):
    if (type(events) is not list or len(events) > MAX_EVENTS
            or (require_nonempty and not events)):
        raise ValueError('invalid bounded recovery event sequence')
    previous = GENESIS
    for number, event in enumerate(events, 1):
        if (type(event) is not dict or set(event) != _EVENT_COLS
                or type(event['sequence']) is not int
                or event['sequence'] != number
                or type(event['base_sequence']) is not int
                or event['base_sequence'] < 1
                or event['previous_event_sha256'] != previous):
            raise ValueError('invalid recovery event order')
        for field in ('request_sha256', 'base_receipt_sha256',
                      'retired_token_sha256', 'event_sha256'):
            _digest(event[field])
        canonical_event = {**{k: v for k, v in event.items()
                              if k != 'event_sha256'}, 'schema': EVENT_SCHEMA}
        if _event_hash(canonical_event) != event['event_sha256']:
            raise ValueError('modified recovery event contents')
        previous = event['event_sha256']
    return events


def snapshot(custodian_db):
    """Check custody and recovery chains in ONE read transaction."""
    with closing(_connect(custodian_db)) as con:
        con.execute('BEGIN')
        try:
            anchor = _history(con)
            if not anchor:
                raise ValueError('missing custodian checkpoint')
            rows = audit_history(con)
            events = _validate_events(
                [_event_from_row(row) for row in rows], require_nonempty=False)
            # Recovery decisions refer to an exact historical custody head.
            # Verify that the recovery chain is also bound to the still
            # retained checkpoint ledger, not merely self-consistent.
            for event in events:
                base = event['base_sequence']
                if (base > len(anchor)
                        or anchor[base-1][3] != event['base_receipt_sha256']):
                    raise ValueError('recovery event not bound to custodian head')
            result = {
                'schema': SNAPSHOT_SCHEMA,
                'custodian_sequence': anchor[-1][0],
                'custodian_receipt_sha256': anchor[-1][3],
                'recovery_events': events,
            }
            con.commit()
            return result
        except Exception:
            con.rollback()
            raise


def _snapshot_input(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SNAPSHOT_BYTES:
        raise ValueError('invalid bounded witness snapshot')
    record = _parse(raw)
    if (type(record) is not dict or set(record) != {
            'schema', 'custodian_sequence',
            'custodian_receipt_sha256', 'recovery_events'}
            or record['schema'] != SNAPSHOT_SCHEMA
            or type(record['custodian_sequence']) is not int
            or record['custodian_sequence'] < 1):
        raise ValueError('invalid witness snapshot schema')
    _digest(record['custodian_receipt_sha256'])
    _validate_events(record['recovery_events'], require_nonempty=False)
    if any(event['base_sequence'] > record['custodian_sequence']
           for event in record['recovery_events']):
        raise ValueError('witness event after supplied custody sequence')
    return record


def _witness_rows(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS recovery_witness_events (
            sequence INTEGER PRIMARY KEY,
            event_bytes BLOB NOT NULL,
            event_sha256 TEXT NOT NULL UNIQUE,
            previous_witness_sha256 TEXT NOT NULL,
            witness_sha256 TEXT NOT NULL UNIQUE
        )""")
    elif con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table'"
        " AND name='recovery_witness_events'").fetchone() is None:
        raise ValueError('missing independently retained witness history')
    cols = {row[1] for row in con.execute(
        'PRAGMA table_info("recovery_witness_events")')}
    if cols != {'sequence', 'event_bytes', 'event_sha256',
                'previous_witness_sha256', 'witness_sha256'}:
        raise ValueError('invalid witness storage schema')
    rows = con.execute(
        'SELECT sequence,event_bytes,event_sha256,'
        'previous_witness_sha256,witness_sha256'
        ' FROM recovery_witness_events ORDER BY sequence LIMIT ?',
        (MAX_EVENTS+1,)).fetchall()
    if len(rows) > MAX_EVENTS:
        raise ValueError('recovery witness is over capacity')
    prev_witness = GENESIS
    prev_event = GENESIS
    for seq, row in enumerate(rows, 1):
        number, raw, event_digest, predecessor, witness_hash = row
        if (type(number) is not int or number != seq
                or type(raw) is not bytes
                or len(raw) > 2048 or predecessor != prev_witness):
            raise ValueError('corrupt independent witness sequence')
        event = _parse(raw)
        _digest(event_digest)
        _digest(witness_hash)
        if (raw != _canonical(event)
                or event['sequence'] != seq
                or event['previous_event_sha256'] != prev_event
                or event['event_sha256'] != event_digest):
            raise ValueError('corrupt independent recovery witness')
        if (type(event) is not dict or set(event) != _EVENT_COLS
                or type(event['sequence']) is not int
                or event['sequence'] != seq
                or type(event['base_sequence']) is not int
                or event['base_sequence'] < 1):
            raise ValueError('invalid witnessed recovery event shape')
        for name in ('request_sha256', 'base_receipt_sha256',
                     'retired_token_sha256'):
            _digest(event[name])
        check = {**{k:v for k,v in event.items() if k != 'event_sha256'},
                 'schema': EVENT_SCHEMA}
        if _event_hash(check) != event_digest:
            raise ValueError('invalid witness event digest')
        computed = hashlib.sha256(
            WITNESS_DOMAIN + bytes.fromhex(prev_witness) + raw).hexdigest()
        if computed != witness_hash:
            raise ValueError('altered witness hash chain')
        prev_event, prev_witness = event_digest, witness_hash
    return rows


def record(witness_db, snapshot_raw):
    """Only append a strict extension of the independently retained prefix."""
    data = _snapshot_input(snapshot_raw)
    events = data['recovery_events']
    with closing(_connect(witness_db, create=True)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            try:
                from .audit_record_witness_fence import require_unfenced
            except ImportError:
                from audit_record_witness_fence import require_unfenced
            require_unfenced(con)
            rows = _witness_rows(con, create=True)
            if not events and not rows:
                raise ValueError('no recovery event available for first witness')
            if len(events) < len(rows):
                raise WitnessRegression('custodian rolled back before witnessed recovery')
            for index, row in enumerate(rows):
                if _canonical(events[index]) != row[1]:
                    raise WitnessRegression('custodian fork differs from witnessed event')
            if len(events) == len(rows):
                con.commit()
                return len(rows), False
            prev = rows[-1][4] if rows else GENESIS
            for event in events[len(rows):]:
                raw = _canonical(event)
                witness_hash = hashlib.sha256(
                    WITNESS_DOMAIN + bytes.fromhex(prev) + raw).hexdigest()
                con.execute(
                    'INSERT INTO recovery_witness_events'
                    ' (sequence,event_bytes,event_sha256,'
                    ' previous_witness_sha256,witness_sha256)'
                    ' VALUES(?,?,?,?,?)',
                    (event['sequence'], raw, event['event_sha256'],
                     prev, witness_hash))
                prev = witness_hash
            con.commit()
            return len(events), True
        except Exception:
            con.rollback()
            raise


def initialize(witness_db):
    """Explicitly initialize a separately administered EMPTY witness.

    Its genesis receipt is required to guard the *first* recovery.
    This must be independently provisioned and pinned; it is not
    automatic bootstrap by a potentially compromised custodian.
    """
    with closing(_connect(witness_db, create=True)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            rows = _witness_rows(con, create=True)
            con.commit()
            return len(rows)
        except Exception:
            con.rollback()
            raise


def _head(witness_db):
    with closing(_connect(witness_db)) as con:
        con.execute('BEGIN')
        try:
            rows = _witness_rows(con)
            con.commit()
            if not rows:
                return 0, GENESIS, GENESIS, []
            return len(rows), rows[-1][2], rows[-1][4], [row[1] for row in rows]
        except Exception:
            con.rollback()
            raise


def _receipt(head, tag):
    return {
        'schema': RECEIPT_SCHEMA, 'witness_tag': _tag(tag),
        'recovery_count': head[0],
        'last_recovery_event_sha256': head[1],
        'witness_chain_sha256': head[2],
    }


def sign_latest(witness_db, private_signing_key, private_output, *, tag):
    """Sign existing committed witness head; safe after lost signing reply."""
    signer = _private_regular_file(private_signing_key)
    if signer.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('oversized private witness key')
    head = _head(witness_db)
    receipt = _receipt(head, tag)
    payload = SIGN_DOMAIN + _canonical(receipt)
    signature = _openssl(signer, payload)
    envelope = {
        'schema': ENVELOPE_SCHEMA, 'receipt': receipt,
        'signature_hex': signature.hex(),
    }
    raw = _canonical(envelope)
    if len(raw) > MAX_SIGNED_BYTES:
        raise ValueError('oversized signed witness receipt')
    _write_new_private(private_output, raw)
    return head[0]


def authenticated_head(witness_db, signed_raw, public_key,
                       pinned_public_pem_sha256, *, tag):
    """Return a validated signed witness prefix without opening custodian DB.

    The signature AND current independent witness state are required.
    A self-consistent old signed receipt is NOT a freshness oracle.
    """
    _digest(pinned_public_pem_sha256)
    if type(signed_raw) is not bytes or not 0 < len(signed_raw) <= MAX_SIGNED_BYTES:
        raise ValueError('invalid private signed witness receipt')
    envelope = _parse(signed_raw)
    head = _head(witness_db)
    expected = _receipt(head, tag)
    if (type(envelope) is not dict or set(envelope) != {
            'schema', 'receipt', 'signature_hex'}
            or envelope['schema'] != ENVELOPE_SCHEMA
            or envelope['receipt'] != expected
            or type(envelope['signature_hex']) is not str
            or not _HEXSIG.fullmatch(envelope['signature_hex'])):
        raise WitnessRegression('stale or altered witness receipt')
    key_path = _private_regular_file(public_key)
    pem = _read_limited(key_path, MAX_PEM_BYTES)
    if not hmac.compare_digest(hashlib.sha256(pem).hexdigest(),
                               pinned_public_pem_sha256):
        raise ValueError('witness public key pin mismatch')
    if not _openssl(
            key_path, SIGN_DOMAIN + _canonical(expected),
            signature=bytes.fromhex(envelope['signature_hex']),
            public_key_bytes=pem):
        raise ValueError('invalid witness Ed25519 signature')
    return head


def check_locked(con, head, *, require_exact=True):
    """Check current custodian rows under the CALLER's SQLite transaction.

    This must be called while the custodian is holding BEGIN IMMEDIATE
    before any administrative mutation. No other writer can replace
    the recovery journal between this check and the local SQL commit.
    """
    anchors = _history(con)
    if not anchors:
        raise WitnessRegression('missing current custodian history')
    from .audit_record_custodian_recovery import audit_history
    recovery = audit_history(con)
    events = [_event_from_row(row) for row in recovery]
    for event in events:
        base = event['base_sequence']
        if (base > len(anchors)
                or anchors[base-1][3] != event['base_receipt_sha256']):
            raise WitnessRegression('recovery event not bound to custodian checkpoint')
    if len(events) < head[0]:
        raise WitnessRegression('custodian recovery journal rolled back')
    for index, historical in enumerate(head[3]):
        if _canonical(events[index]) != historical:
            raise WitnessRegression('custodian recovery journal fork')
    if require_exact and len(events) != head[0]:
        raise WitnessRegression('new recovery event not independently witnessed')
    return len(events)


def verify(custodian_db, witness_db, signed_raw, public_key,
           pinned_public_pem_sha256, *, tag, require_exact=False):
    """Read-only current recovery verification against signed witness head."""
    head = authenticated_head(
        witness_db, signed_raw, public_key, pinned_public_pem_sha256, tag=tag)
    with closing(_connect(custodian_db)) as con:
        con.execute('BEGIN')
        try:
            count = check_locked(con, head, require_exact=require_exact)
            con.commit()
        except Exception:
            con.rollback()
            raise
    return {
        'verified_recoveries': head[0],
        'unwitnessed_recoveries': count-head[0],
        'current_custodian_recovery_chain_matches_witness': True,
        'independent_witness_operated_by_separate_actor': False,
        'global_rollback_prevention_guaranteed': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('initialize')
    p.add_argument('witness_database', type=Path)
    p = sub.add_parser('capture')
    p.add_argument('custodian_database', type=Path)
    p.add_argument('private_snapshot_output', type=Path)
    p = sub.add_parser('record')
    p.add_argument('witness_database', type=Path)
    p.add_argument('private_snapshot_input', type=Path)
    p = sub.add_parser('sign')
    p.add_argument('witness_database', type=Path)
    p.add_argument('private_witness_signing_key', type=Path)
    p.add_argument('private_signed_receipt_output', type=Path)
    p.add_argument('--witness-tag', required=True)
    p = sub.add_parser('verify')
    p.add_argument('custodian_database', type=Path)
    p.add_argument('witness_database', type=Path)
    p.add_argument('private_signed_receipt', type=Path)
    p.add_argument('pinned_witness_public_key', type=Path)
    p.add_argument('trusted_public_pem_sha256')
    p.add_argument('--witness-tag', required=True)
    p.add_argument('--require-exact', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'initialize':
            count = initialize(args.witness_database)
            status, result = 0, {
                'private_witness_initialized': True,
                'witnessed_recovery_count': count,
            }
        elif args.mode == 'capture':
            data = snapshot(args.custodian_database)
            if not data['recovery_events']:
                raise ValueError('no recovery events to witness')
            raw = _canonical(data)
            if len(raw) > MAX_SNAPSHOT_BYTES:
                raise ValueError('snapshot size exceeds bound')
            _write_new_private(args.private_snapshot_output, raw)
            status, result = 0, {'private_snapshot_prepared': True}
        elif args.mode == 'record':
            raw = _read_limited(
                _private_regular_file(args.private_snapshot_input),
                MAX_SNAPSHOT_BYTES)
            count, fresh = record(args.witness_database, raw)
            status, result = 0, {
                'witness_history_accepted': True,
                'idempotent_record': not fresh,
                'witnessed_recovery_count': count}
        elif args.mode == 'sign':
            count = sign_latest(
                args.witness_database, args.private_witness_signing_key,
                args.private_signed_receipt_output,
                tag=args.witness_tag)
            status, result = 0, {
                'private_witness_receipt_signed': True,
                'witnessed_recovery_count': count}
        else:
            raw = _read_limited(
                _private_regular_file(args.private_signed_receipt),
                MAX_SIGNED_BYTES)
            info = verify(args.custodian_database, args.witness_database,
                          raw, args.pinned_witness_public_key,
                          args.trusted_public_pem_sha256,
                          tag=args.witness_tag, require_exact=args.require_exact)
            status, result = 0, info
    except WitnessRegression:
        status, result = 1, {'independent_recovery_witness_mismatch': True}
    except (OSError, ValueError, TypeError, KeyError, OverflowError,
            UnicodeError, IndexError, RecursionError, sqlite3.Error):
        status, result = 2, {
            'valid_input': False, 'error_code': 'invalid_private_witness_input'}
    result.update({
        'schema': REPORT_SCHEMA,
        'private_tokens_or_keys_emitted': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'independent_witness_deployed': False,
    })
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
