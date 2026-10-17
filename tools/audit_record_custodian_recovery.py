"""Stage-256 two-admin, signature-gated recovery of an orphaned reservation.

The custodian checks two independently pinned Ed25519 administrator public
keys, the same exact signed recovery request, and the current custody head
inside BEGIN IMMEDIATE. A hash-linked audit entry is committed in the same
transaction as retirement of the orphaned reservation. No automatic expiry,
generic cancellation, or legacy write access is created by this recovery.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_anchor_handoff import _canonical, _history, GENESIS
    from .audit_record_custodian_reservation import reservation_row, ReservationConflict
    from .audit_record_capture_stream_binding import _digest, _parse, _read_limited
    from .audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from .audit_record_verifier_checkpoint import _private_regular_file, _write_new_private
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import _canonical, _history, GENESIS
    from audit_record_custodian_reservation import reservation_row, ReservationConflict
    from audit_record_capture_stream_binding import _digest, _parse, _read_limited
    from audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from audit_record_verifier_checkpoint import _private_regular_file, _write_new_private

REQUEST_SCHEMA = 'wild-arms-ps1-custodian-recovery-request-v1'
APPROVAL_SCHEMA = 'wild-arms-ps1-custodian-recovery-approval-v1'
EVENT_SCHEMA = 'wild-arms-ps1-custodian-recovery-event-v1'
REPORT_SCHEMA = 'wild-arms-ps1-custodian-recovery-audit-v1'
DOMAIN = b'wild-arms-ps1-custodian-recovery-approval-v1\x00'
EVENT_DOMAIN = b'wild-arms-ps1-custodian-recovery-event-v1\x00'
MAX_REQUEST = 2048
MAX_APPROVAL = 1024
MAX_EVENTS = 512
_HEX128 = re.compile(r'[0-9a-f]{32}\Z')
_HEXSIG = re.compile(r'[0-9a-f]{128}\Z')
_REQUEST_FIELDS = {'schema', 'expected_sequence', 'expected_receipt_sha256',
                   'expected_token_sha256', 'recovery_nonce', 'reason'}
_EVENT_FIELDS = {'schema', 'sequence', 'request_sha256', 'base_sequence',
                 'base_receipt_sha256', 'retired_token_sha256',
                 'previous_event_sha256'}


class RecoveryConflict(ReservationConflict):
    """The custody state no longer matches two-admin recovery approval."""


def _request(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST:
        raise ValueError('invalid bounded private recovery request')
    value = _parse(raw)
    if (type(value) is not dict or set(value) != _REQUEST_FIELDS
            or value['schema'] != REQUEST_SCHEMA
            or type(value['expected_sequence']) is not int
            or value['expected_sequence'] < 1
            or value['reason'] != 'irrecoverable-reservation-token'
            or type(value['recovery_nonce']) is not str
            or not _HEX128.fullmatch(value['recovery_nonce'])):
        raise ValueError('invalid recovery request')
    _digest(value['expected_receipt_sha256'])
    _digest(value['expected_token_sha256'])
    return value


def _event(seq, req_digest, request, previous):
    return {
        'schema': EVENT_SCHEMA,
        'sequence': seq,
        'request_sha256': req_digest,
        'base_sequence': request['expected_sequence'],
        'base_receipt_sha256': request['expected_receipt_sha256'],
        'retired_token_sha256': request['expected_token_sha256'],
        'previous_event_sha256': previous,
    }


def _event_hash(event):
    return hashlib.sha256(EVENT_DOMAIN + _canonical(event)).hexdigest()


def audit_history(con, *, create=False):
    """Check the entire bounded recovery chain before custodian mutation."""
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='custodian_recovery_history'").fetchone() is not None
    if not exists and not create:
        return []
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS custodian_recovery_history (
            sequence INTEGER PRIMARY KEY,
            request_sha256 TEXT NOT NULL UNIQUE,
            base_sequence INTEGER NOT NULL,
            base_receipt_sha256 TEXT NOT NULL,
            retired_token_sha256 TEXT NOT NULL,
            previous_event_sha256 TEXT NOT NULL,
            event_sha256 TEXT NOT NULL UNIQUE
        )""")
    cols = {entry[1] for entry in con.execute(
        'PRAGMA table_info("custodian_recovery_history")')}
    if cols != {'sequence', 'request_sha256', 'base_sequence',
                'base_receipt_sha256', 'retired_token_sha256',
                'previous_event_sha256', 'event_sha256'}:
        raise ValueError('invalid custodian recovery journal schema')
    rows = con.execute(
        'SELECT sequence,request_sha256,base_sequence,base_receipt_sha256,'
        'retired_token_sha256,previous_event_sha256,event_sha256'
        ' FROM custodian_recovery_history ORDER BY sequence LIMIT ?',
        (MAX_EVENTS + 1,)).fetchall()
    if len(rows) > MAX_EVENTS:
        raise ValueError('custodian recovery journal capacity exceeded')
    previous = GENESIS
    for seq, (number, req_hash, base_seq, base_hash, token_hash,
              linked, event_hash) in enumerate(rows, 1):
        if (type(number) is not int or number != seq
                or type(base_seq) is not int or base_seq < 1
                or linked != previous):
            raise ValueError('invalid custodian recovery journal chain')
        for value in (req_hash, base_hash, token_hash, event_hash):
            _digest(value)
        recorded = {
            'schema': EVENT_SCHEMA, 'sequence': seq,
            'request_sha256': req_hash, 'base_sequence': base_seq,
            'base_receipt_sha256': base_hash,
            'retired_token_sha256': token_hash,
            'previous_event_sha256': linked,
        }
        if _event_hash(recorded) != event_hash:
            raise ValueError('custodian recovery journal modified')
        previous = event_hash
    return rows


def prepare(custodian_db, output):
    """Operator-invoked private proposal; does not change the custodian."""
    with closing(_connect(custodian_db)) as con:
        con.execute('BEGIN')
        try:
            history = _history(con)
            audit_history(con)
            reserved = reservation_row(con)
            if (not history or reserved is None
                    or reserved[4] != 'reserved'
                    or (reserved[1], reserved[2]) != (history[-1][0], history[-1][3])):
                raise RecoveryConflict('no orphaned reservation at current head')
            request = {
                'schema': REQUEST_SCHEMA, 'expected_sequence': reserved[1],
                'expected_receipt_sha256': reserved[2],
                'expected_token_sha256': reserved[3],
                'recovery_nonce': secrets.token_hex(16),
                'reason': 'irrecoverable-reservation-token',
            }
            con.commit()
        except Exception:
            con.rollback()
            raise
    _write_new_private(output, _canonical(request))
    return request['expected_sequence']


def _signed_request_body(admin_id, request_sha256):
    return {
        'schema': APPROVAL_SCHEMA, 'admin_id': _tag(admin_id),
        'request_sha256': request_sha256,
    }


def approve(request_raw, admin_id, private_key, private_output):
    """Admin signs the request hash; no custodian write side effect."""
    _request(request_raw)
    path = _private_regular_file(private_key)
    if path.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('invalid private admin signing key')
    body = _signed_request_body(admin_id, hashlib.sha256(request_raw).hexdigest())
    signature = _openssl(path, DOMAIN + _canonical(body))
    envelope = {**body, 'signature_hex': signature.hex()}
    _write_new_private(private_output, _canonical(envelope))


def _verify_approval(request_raw, approval_raw, admin_id,
                     public_key_path, expected_pin):
    if type(approval_raw) is not bytes or not 0 < len(approval_raw) <= MAX_APPROVAL:
        raise ValueError('invalid bounded admin approval')
    _digest(expected_pin)
    obj = _parse(approval_raw)
    body = _signed_request_body(
        admin_id, hashlib.sha256(request_raw).hexdigest())
    if (type(obj) is not dict or set(obj) != set(body) | {'signature_hex'}
            or any(obj[field] != value for field, value in body.items())
            or type(obj['signature_hex']) is not str
            or not _HEXSIG.fullmatch(obj['signature_hex'])):
        raise ValueError('wrong or malformed administrator approval')
    key = _private_regular_file(public_key_path)
    pem = _read_limited(key, MAX_PEM_BYTES)
    if not hmac.compare_digest(hashlib.sha256(pem).hexdigest(), expected_pin):
        raise ValueError('administrator public key pin mismatch')
    if not _openssl(key, DOMAIN + _canonical(body),
                    signature=bytes.fromhex(obj['signature_hex']),
                    public_key_bytes=pem):
        raise ValueError('invalid administrator signature')
    return expected_pin


def recover(custodian_db, request_raw, approval_a, approval_b,
            admin_a_id, admin_a_public, admin_a_pin,
            admin_b_id, admin_b_public, admin_b_pin, *, witness_head=None):
    """Atomically retire an orphaned reservation.

    Optional witness enforcement is inside the *same* local write transaction
    as administrative recovery. Legacy calls remain unguarded.
    """
    request = _request(request_raw)
    if _tag(admin_a_id) == _tag(admin_b_id) or admin_a_pin == admin_b_pin:
        raise ValueError('two distinct independently pinned admin keys required')
    first = _verify_approval(request_raw, approval_a, admin_a_id,
                             admin_a_public, admin_a_pin)
    second = _verify_approval(request_raw, approval_b, admin_b_id,
                              admin_b_public, admin_b_pin)
    if first == second:
        raise ValueError('duplicate administrator key')
    req_hash = hashlib.sha256(request_raw).hexdigest()
    with closing(_connect(custodian_db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            if witness_head is not None:
                try:
                    from .audit_record_recovery_witness import check_locked
                except ImportError:
                    from audit_record_recovery_witness import check_locked
                try:
                    check_locked(con, witness_head, require_exact=True)
                except ValueError as exc:
                    raise RecoveryConflict('witness continuity check refused recovery') from exc
            rows = _history(con)
            events = audit_history(con, create=True)
            reserved = reservation_row(con)
            if (not rows or reserved is None or reserved[4] != 'reserved'
                    or (rows[-1][0], rows[-1][3]) != (
                        request['expected_sequence'],
                        request['expected_receipt_sha256'])
                    or (reserved[1], reserved[2], reserved[3]) != (
                        request['expected_sequence'],
                        request['expected_receipt_sha256'],
                        request['expected_token_sha256'])):
                raise RecoveryConflict('reservation changed since approvals')
            if len(events) >= MAX_EVENTS:
                raise ValueError('recovery journal at capacity')
            seq = len(events) + 1
            prev = events[-1][6] if events else GENESIS
            event = _event(seq, req_hash, request, prev)
            con.execute(
                'INSERT INTO custodian_recovery_history'
                ' (sequence,request_sha256,base_sequence,'
                'base_receipt_sha256,retired_token_sha256,'
                'previous_event_sha256,event_sha256)'
                ' VALUES(?,?,?,?,?,?,?)',
                (seq, req_hash, request['expected_sequence'],
                 request['expected_receipt_sha256'],
                 request['expected_token_sha256'], prev, _event_hash(event)))
            if con.execute(
                    "DELETE FROM custodian_reservation WHERE slot=1"
                    " AND status='reserved' AND token_sha256=?",
                    (request['expected_token_sha256'],)).rowcount != 1:
                raise RecoveryConflict('reservation disappeared during recovery')
            con.commit()
            return seq
        except Exception:
            con.rollback()
            raise


def recover_with_witness(custodian_db, request_raw, approval_a, approval_b,
                         admin_a_id, admin_a_public, admin_a_pin,
                         admin_b_id, admin_b_public, admin_b_pin,
                         *, witness_db, signed_witness_raw,
                         witness_public_key, witness_public_pem_pin,
                         witness_tag):
    """Require pinned signed witness state; compare it inside recovery TX."""
    try:
        from .audit_record_recovery_witness import authenticated_head
    except ImportError:
        from audit_record_recovery_witness import authenticated_head
    try:
        head = authenticated_head(
            witness_db, signed_witness_raw,
            witness_public_key, witness_public_pem_pin, tag=witness_tag)
    except ValueError as exc:
        raise RecoveryConflict('witness signature or freshness check refused recovery') from exc
    return recover(
        custodian_db, request_raw, approval_a, approval_b,
        admin_a_id, admin_a_public, admin_a_pin,
        admin_b_id, admin_b_public, admin_b_pin,
        witness_head=head)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    p = modes.add_parser('prepare')
    p.add_argument('custodian_db', type=Path)
    p.add_argument('private_request_out', type=Path)
    p = modes.add_parser('approve')
    p.add_argument('private_request', type=Path)
    p.add_argument('admin_id')
    p.add_argument('private_admin_key', type=Path)
    p.add_argument('private_approval_out', type=Path)
    for mode in ('recover', 'recover-guarded'):
        p = modes.add_parser(mode)
        p.add_argument('custodian_db', type=Path)
        p.add_argument('private_request', type=Path)
        p.add_argument('private_approval_a', type=Path)
        p.add_argument('private_approval_b', type=Path)
        for name in ('a', 'b'):
            p.add_argument('admin_' + name + '_id')
            p.add_argument('admin_' + name + '_public_key', type=Path)
            p.add_argument('admin_' + name + '_trusted_pem_sha256')
        if mode == 'recover-guarded':
            p.add_argument('independent_witness_db', type=Path)
            p.add_argument('private_signed_witness_receipt', type=Path)
            p.add_argument('pinned_witness_public_pem', type=Path)
            p.add_argument('trusted_witness_public_pem_sha256')
            p.add_argument('--witness-tag', required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'prepare':
            number = prepare(args.custodian_db, args.private_request_out)
            result, code = {'private_recovery_request_prepared': True,
                            'custody_sequence': number}, 0
        elif args.mode == 'approve':
            raw = _read_limited(_private_regular_file(args.private_request),
                                MAX_REQUEST)
            approve(raw, args.admin_id, args.private_admin_key,
                    args.private_approval_out)
            result, code = {'private_admin_approval_created': True}, 0
        else:
            raw = _read_limited(_private_regular_file(args.private_request),
                                MAX_REQUEST)
            sig_a = _read_limited(_private_regular_file(args.private_approval_a),
                                  MAX_APPROVAL)
            sig_b = _read_limited(_private_regular_file(args.private_approval_b),
                                  MAX_APPROVAL)
            public_args = (
                args.custodian_db, raw, sig_a, sig_b,
                args.admin_a_id, args.admin_a_public_key,
                args.admin_a_trusted_pem_sha256,
                args.admin_b_id, args.admin_b_public_key,
                args.admin_b_trusted_pem_sha256)
            if args.mode == 'recover-guarded':
                signed = _read_limited(
                    _private_regular_file(args.private_signed_witness_receipt),
                    2048)
                number = recover_with_witness(
                    *public_args, witness_db=args.independent_witness_db,
                    signed_witness_raw=signed,
                    witness_public_key=args.pinned_witness_public_pem,
                    witness_public_pem_pin=args.trusted_witness_public_pem_sha256,
                    witness_tag=args.witness_tag)
            else:
                number = recover(*public_args)
            result, code = {'orphan_reservation_retired': True,
                            'witness_guarded_recovery': args.mode == 'recover-guarded',
                            'recovery_journal_sequence': number}, 0
    except (RecoveryConflict, ReservationConflict):
        result, code = {'recovery_refused_due_to_changed_state': True}, 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            OverflowError, RecursionError, sqlite3.Error):
        result, code = {'valid_input': False,
                        'error_code': 'invalid_private_recovery_input'}, 2
    result.update({
        'schema': REPORT_SCHEMA,
        'admin_keys_independently_provisioned_by_repo': False,
        'external_immutable_audit_log_provided': False,
        'automatic_orphan_release_performed': False,
        'legacy_writes_reenabled': False,
        'independent_custodian_deployed': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_tokens_keys_or_hashes_printed': False,
    })
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
