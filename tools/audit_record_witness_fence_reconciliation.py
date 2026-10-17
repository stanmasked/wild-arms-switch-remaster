"""Offline two-administrator reconciliation of an orphaned witness fence.

ONLY proven applied custody operations can be reconciled. In particular an
uncommitted/indeterminate custody mutation is NOT an authorization to release
a fence: concurrent or restarted custody writers must be quiesced separately.
No automatic expiration, generic reset or production service is provided.

A separately pinned custodian Ed25519 key signs the exact request's observed
committed result. Two different pinned administrator keys approve the same
nonce-bearing proposal. Witness-side BEGIN IMMEDIATE verifies the exact
existing fence and appends a hash-linked reconciliation record in the SAME
commit that retires it. Secrets are never emitted by the CLI.
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
    from .audit_record_capture_stream_binding import _digest, _parse, _read_limited, _sha
    from .audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from .audit_record_verifier_checkpoint import _private_regular_file, _write_new_private
    from .audit_record_custodian_reservation import reservation_row, token_hash
    from .audit_record_custodian_recovery import audit_history
    from .audit_record_custodian_tls import REQUEST_SCHEMA, _b64_decode
    from .audit_record_witness_fence import _owner, _fence_row, FenceConflict
    from .audit_record_recovery_witness import _witness_rows
    from .audit_record_capture_stream_binding import MAX_STREAM_BYTES
    from .audit_record_verifier_checkpoint import MAX_CHECKPOINT_BYTES
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import _canonical, _history, GENESIS
    from audit_record_capture_stream_binding import _digest, _parse, _read_limited, _sha
    from audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from audit_record_verifier_checkpoint import _private_regular_file, _write_new_private
    from audit_record_custodian_reservation import reservation_row, token_hash
    from audit_record_custodian_recovery import audit_history
    from audit_record_custodian_tls import REQUEST_SCHEMA, _b64_decode
    from audit_record_witness_fence import _owner, _fence_row, FenceConflict
    from audit_record_recovery_witness import _witness_rows
    from audit_record_capture_stream_binding import MAX_STREAM_BYTES
    from audit_record_verifier_checkpoint import MAX_CHECKPOINT_BYTES

OUTCOME_SCHEMA = 'wild-arms-ps1-witness-fence-custody-outcome-v1'
REQUEST_RECOVERY_SCHEMA = 'wild-arms-ps1-witness-fence-reconcile-request-v1'
APPROVAL_SCHEMA = 'wild-arms-ps1-witness-fence-reconcile-approval-v1'
EVENT_SCHEMA = 'wild-arms-ps1-witness-fence-reconcile-event-v1'
REPORT_SCHEMA = 'wild-arms-ps1-witness-fence-reconcile-report-v1'
CUSTODY_DOMAIN = b'wild-arms-ps1-witness-fence-custody-outcome-v1\x00'
ADMIN_DOMAIN = b'wild-arms-ps1-witness-fence-admin-approval-v1\x00'
EVENT_DOMAIN = b'wild-arms-ps1-witness-fence-reconcile-event-v1\x00'
REQUEST_DOMAIN = b'wild-arms-ps1-custody-request-fence-v1\x00'
MAX_ORIGINAL_REQUEST = 1024 * 1024
MAX_OUTCOME = 2048
MAX_REQUEST = 2048
MAX_APPROVAL = 1024
MAX_EVENTS = 512
_HEX = re.compile(r'[0-9a-f]{32}\Z')
_SIGNATURE = re.compile(r'[0-9a-f]{128}\Z')
EVENT_KEYS = ('sequence', 'request_sha256', 'custody_request_sha256',
              'custody_outcome_sha256', 'retired_owner_sha256',
              'previous_event_sha256', 'event_sha256')


class ReconciliationConflict(FenceConflict):
    """Existing fence, trusted evidence, or admin consent no longer matches."""


def _original(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ORIGINAL_REQUEST:
        raise ValueError('invalid bounded original custody request')
    item = _parse(raw)
    if (type(item) is not dict or item.get('schema') != REQUEST_SCHEMA
            or item.get('action') not in ('reserve', 'deposit-reserved')
            or type(item.get('request_id')) is not str
            or not _HEX.fullmatch(item['request_id'])
            or type(item.get('expected_sequence')) is not int
            or item['expected_sequence'] < 1
            or type(item.get('reservation_token')) is not str):
        raise ValueError('unsupported or malformed custody request')
    _owner(item['request_id'])
    token_hash(item['reservation_token'])
    _digest(item.get('expected_receipt_sha256'))
    fields = {'schema', 'action', 'request_id', 'expected_sequence',
              'expected_receipt_sha256', 'reservation_token'}
    if item['action'] == 'deposit-reserved':
        fields.add('checkpoint_b64')
        offered = _b64_decode(item.get('checkpoint_b64'), MAX_CHECKPOINT_BYTES)
    else:
        offered = None
    if set(item) != fields or raw != _canonical(item):
        raise ValueError('noncanonical private original custody request')
    return item, offered


def _request_digest(raw):
    return hashlib.sha256(REQUEST_DOMAIN + raw).hexdigest()


def _signed(envelope_raw, schema, context, expected_pin, public_key):
    if type(envelope_raw) is not bytes or not 0 < len(envelope_raw) <= MAX_OUTCOME:
        raise ValueError('invalid bounded signed proof')
    envelope = _parse(envelope_raw)
    if (type(envelope) is not dict or set(envelope) !=
            {'schema', 'body', 'signature_hex'}
            or envelope['schema'] != schema
            or type(envelope['body']) is not dict
            or type(envelope['signature_hex']) is not str
            or not _SIGNATURE.fullmatch(envelope['signature_hex'])):
        raise ValueError('invalid signed proof envelope')
    _digest(expected_pin)
    pub_path = _private_regular_file(public_key)
    raw = _read_limited(pub_path, MAX_PEM_BYTES)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_pin):
        raise ValueError('untrusted public PEM pin')
    if not _openssl(pub_path, context + _canonical(envelope['body']),
                    signature=bytes.fromhex(envelope['signature_hex']),
                    public_key_bytes=raw):
        raise ValueError('invalid independent Ed25519 signature')
    return envelope['body']


def _sign(body, schema, context, private_key, output):
    key = _private_regular_file(private_key)
    if key.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('oversized private Ed25519 key')
    envelope = {'schema': schema, 'body': body,
                'signature_hex': _openssl(
                    key, context + _canonical(body)).hex()}
    _write_new_private(output, _canonical(envelope))


def _custody_applied(con, request, offered):
    rows = _history(con)
    audit_history(con)
    reservation = reservation_row(con)
    if not rows or reservation is None:
        raise ReconciliationConflict('no independently observable custody commit')
    seq, receipt = request['expected_sequence'], request['expected_receipt_sha256']
    thash = token_hash(request['reservation_token'])
    if (reservation[1], reservation[2], reservation[3]) != (seq, receipt, thash):
        raise ReconciliationConflict('custody reservation no longer matches request')
    if request['action'] == 'reserve':
        if reservation[4] == 'reserved':
            if (rows[-1][0], rows[-1][3]) != (seq, receipt):
                raise ReconciliationConflict('custody head changed after reserve')
            result = 'reservation-observed'
        elif (reservation[4] == 'committed'
              and reservation[1] + 1 == rows[-1][0]
              and rows[-1][2] == receipt
              and reservation[5] == rows[-1][1]):
            result = 'reservation-followed-by-commit'
        else:
            raise ReconciliationConflict('original reserve not proved')
    else:
        if (reservation[4] != 'committed'
                or (rows[-1][0], rows[-1][2], rows[-1][1]) != (
                    seq + 1, receipt, _sha(offered))
                or reservation[5] != _sha(offered)):
            raise ReconciliationConflict('exact checkpoint deposit not committed')
        result = 'checkpoint-committed'
    return result, rows[-1][0], rows[-1][3]


def attest_applied(custodian_db, original_raw, signing_key, output,
                   *, custodian_tag):
    """Only custody state proved applied can produce a signed outcome."""
    request, offered = _original(original_raw)
    with closing(_connect(custodian_db)) as con:
        con.execute('BEGIN')
        try:
            result, count, receipt = _custody_applied(con, request, offered)
            con.commit()
        except Exception:
            con.rollback()
            raise
    body = {
        'schema': OUTCOME_SCHEMA,
        'custodian_tag': _tag(custodian_tag),
        'custody_request_sha256': _request_digest(original_raw),
        'fence_owner_sha256': _owner(request['request_id']),
        'resolution': result,
        'current_sequence': count,
        'current_receipt_sha256': receipt,
    }
    _sign(body, OUTCOME_SCHEMA, CUSTODY_DOMAIN, signing_key, output)
    return result


def verify_applied(original_raw, outcome_raw, custodian_public, custodian_pin,
                   *, custodian_tag):
    request, offered = _original(original_raw)
    body = _signed(outcome_raw, OUTCOME_SCHEMA, CUSTODY_DOMAIN,
                   custodian_pin, custodian_public)
    if (set(body) != {'schema', 'custodian_tag', 'custody_request_sha256',
                      'fence_owner_sha256', 'resolution', 'current_sequence',
                      'current_receipt_sha256'}
            or body['schema'] != OUTCOME_SCHEMA
            or body['custodian_tag'] != _tag(custodian_tag)
            or body['custody_request_sha256'] != _request_digest(original_raw)
            or body['fence_owner_sha256'] != _owner(request['request_id'])
            or type(body['current_sequence']) is not int
            or body['current_sequence'] < 1):
        raise ValueError('signed custody result not for exact request')
    _digest(body['current_receipt_sha256'])
    base = request['expected_sequence']
    if request['action'] == 'reserve':
        if (body['resolution'] == 'reservation-observed'
                and body['current_sequence'] == base
                and body['current_receipt_sha256'] ==
                    request['expected_receipt_sha256']):
            pass
        elif (body['resolution'] == 'reservation-followed-by-commit'
              and body['current_sequence'] == base + 1):
            pass
        else:
            raise ValueError('custody result does not prove reserve applied')
    elif (body['resolution'] != 'checkpoint-committed'
          or body['current_sequence'] != base + 1):
        raise ValueError('custody result does not prove exact deposit')
    return body


def _proposal(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST:
        raise ValueError('invalid bounded reconciliation proposal')
    obj = _parse(raw)
    if (type(obj) is not dict or set(obj) != {
            'schema', 'recovery_nonce', 'reason',
            'fence_owner_sha256', 'custody_request_sha256',
            'custody_outcome_sha256', 'witness_count',
            'witness_chain_sha256'}
            or obj['schema'] != REQUEST_RECOVERY_SCHEMA
            or obj['reason'] != 'confirmed-applied-custody-operation'
            or type(obj['recovery_nonce']) is not str
            or not _HEX.fullmatch(obj['recovery_nonce'])
            or type(obj['witness_count']) is not int
            or obj['witness_count'] < 0):
        raise ValueError('invalid reconciliation proposal schema')
    for field in ('fence_owner_sha256', 'custody_request_sha256',
                  'custody_outcome_sha256', 'witness_chain_sha256'):
        _digest(obj[field])
    if raw != _canonical(obj):
        raise ValueError('noncanonical reconciliation proposal')
    return obj


def _audit(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS witness_fence_reconciliations (
            sequence INTEGER PRIMARY KEY,
            request_sha256 TEXT NOT NULL UNIQUE,
            custody_request_sha256 TEXT NOT NULL,
            custody_outcome_sha256 TEXT NOT NULL,
            retired_owner_sha256 TEXT NOT NULL,
            previous_event_sha256 TEXT NOT NULL,
            event_sha256 TEXT NOT NULL UNIQUE
        )""")
    elif con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                     "name='witness_fence_reconciliations'").fetchone() is None:
        return []
    keys = {r[1] for r in con.execute(
        'PRAGMA table_info("witness_fence_reconciliations")')}
    if keys != set(EVENT_KEYS):
        raise ValueError('invalid reconciliation journal columns')
    rows = con.execute(
        'SELECT sequence,request_sha256,custody_request_sha256,'
        'custody_outcome_sha256,retired_owner_sha256,'
        'previous_event_sha256,event_sha256'
        ' FROM witness_fence_reconciliations ORDER BY sequence LIMIT ?',
        (MAX_EVENTS + 1,)).fetchall()
    if len(rows) > MAX_EVENTS:
        raise ValueError('reconciliation journal capacity exceeded')
    prior = GENESIS
    for i, row in enumerate(rows, 1):
        if (type(row[0]) is not int or row[0] != i or row[5] != prior):
            raise ValueError('corrupt reconciliation journal order')
        for value in row[1:]:
            _digest(value)
        payload = dict(zip(EVENT_KEYS[:-1], row[:-1]))
        payload['schema'] = EVENT_SCHEMA
        if hashlib.sha256(EVENT_DOMAIN + _canonical(payload)).hexdigest() != row[-1]:
            raise ValueError('corrupt reconciliation audit hash')
        prior = row[-1]
    return rows


def prepare(witness_db, original_raw, outcome_raw, custodian_public,
            custodian_pin, private_output, *, custodian_tag):
    req, _ = _original(original_raw)
    verify_applied(original_raw, outcome_raw, custodian_public,
                   custodian_pin, custodian_tag=custodian_tag)
    with closing(_connect(witness_db)) as con:
        con.execute('BEGIN')
        try:
            rows = _witness_rows(con)
            _audit(con)
            fence = _fence_row(con)
            if fence is None or (fence[1], fence[2]) != (
                    _owner(req['request_id']), _request_digest(original_raw)):
                raise ReconciliationConflict('no exact outstanding witness fence')
            proposal = {
                'schema': REQUEST_RECOVERY_SCHEMA,
                'recovery_nonce': secrets.token_hex(16),
                'reason': 'confirmed-applied-custody-operation',
                'fence_owner_sha256': fence[1],
                'custody_request_sha256': fence[2],
                'custody_outcome_sha256': _sha(outcome_raw),
                'witness_count': len(rows),
                'witness_chain_sha256': rows[-1][4] if rows else GENESIS,
            }
            if (fence[3], fence[4]) != (
                    proposal['witness_count'],
                    proposal['witness_chain_sha256']):
                raise ReconciliationConflict('fenced witness head changed')
            con.commit()
        except Exception:
            con.rollback()
            raise
    _write_new_private(private_output, _canonical(proposal))


def approve(proposal_raw, admin_id, admin_key, private_output):
    _proposal(proposal_raw)
    identity = _tag(admin_id)
    body = {
        'schema': APPROVAL_SCHEMA, 'admin_id': identity,
        'request_sha256': _sha(proposal_raw),
    }
    _sign(body, APPROVAL_SCHEMA, ADMIN_DOMAIN, admin_key, private_output)


def _approval(proposal_raw, raw, name, public, pin):
    body = _signed(raw, APPROVAL_SCHEMA, ADMIN_DOMAIN, pin, public)
    if body != {
            'schema': APPROVAL_SCHEMA,
            'admin_id': _tag(name),
            'request_sha256': _sha(proposal_raw)}:
        raise ValueError('incorrect independent administrative approval')


def recover(witness_db, original_raw, outcome_raw, proposal_raw,
            admin_a_raw, admin_b_raw, custodian_public, custodian_pin,
            admin_a_name, admin_a_public, admin_a_pin,
            admin_b_name, admin_b_public, admin_b_pin, *, custodian_tag):
    """Remove ONLY exactly attested completed fence, committing audit with it."""
    request, _ = _original(original_raw)
    verified = verify_applied(
        original_raw, outcome_raw, custodian_public, custodian_pin,
        custodian_tag=custodian_tag)
    proposal = _proposal(proposal_raw)
    if (proposal['custody_request_sha256'] != _request_digest(original_raw)
            or proposal['fence_owner_sha256'] != _owner(request['request_id'])
            or proposal['custody_outcome_sha256'] != _sha(outcome_raw)):
        raise ReconciliationConflict('approved request/evidence mismatch')
    if (_tag(admin_a_name) == _tag(admin_b_name)
            or admin_a_pin == admin_b_pin):
        raise ValueError('two distinct administrator identities and keys required')
    _approval(proposal_raw, admin_a_raw, admin_a_name,
              admin_a_public, admin_a_pin)
    _approval(proposal_raw, admin_b_raw, admin_b_name,
              admin_b_public, admin_b_pin)
    with closing(_connect(witness_db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            rows = _witness_rows(con)
            history = _audit(con, create=True)
            fence = _fence_row(con)
            if (fence is None
                    or (fence[1], fence[2], fence[3], fence[4]) != (
                        proposal['fence_owner_sha256'],
                        proposal['custody_request_sha256'],
                        proposal['witness_count'],
                        proposal['witness_chain_sha256'])
                    or (len(rows), rows[-1][4] if rows else GENESIS) != (
                        proposal['witness_count'],
                        proposal['witness_chain_sha256'])):
                raise ReconciliationConflict('witness fence or head changed')
            if (len(history) >= MAX_EVENTS
                    or any(r[2] == proposal['custody_request_sha256']
                           for r in history)):
                raise ReconciliationConflict('duplicate or exhausted reconciliation')
            sequence = len(history) + 1
            event = {
                'schema': EVENT_SCHEMA, 'sequence': sequence,
                'request_sha256': _sha(proposal_raw),
                'custody_request_sha256': proposal['custody_request_sha256'],
                'custody_outcome_sha256': proposal['custody_outcome_sha256'],
                'retired_owner_sha256': proposal['fence_owner_sha256'],
                'previous_event_sha256': history[-1][-1] if history else GENESIS,
            }
            digest = hashlib.sha256(EVENT_DOMAIN + _canonical(event)).hexdigest()
            con.execute(
                'INSERT INTO witness_fence_reconciliations '
                '(sequence,request_sha256,custody_request_sha256,'
                'custody_outcome_sha256,retired_owner_sha256,'
                'previous_event_sha256,event_sha256) VALUES(?,?,?,?,?,?,?)',
                (sequence, event['request_sha256'],
                 event['custody_request_sha256'],
                 event['custody_outcome_sha256'],
                 event['retired_owner_sha256'],
                 event['previous_event_sha256'], digest))
            if con.execute(
                'DELETE FROM recovery_witness_fence'
                ' WHERE slot=1 AND owner_sha256=? AND custody_request_sha256=?',
                (fence[1], fence[2])).rowcount != 1:
                raise ReconciliationConflict('custody fence raced during recovery')
            con.commit()
            return sequence
        except Exception:
            con.rollback()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    p = modes.add_parser('attest')
    p.add_argument('custodian_database', type=Path)
    p.add_argument('original_custody_request', type=Path)
    p.add_argument('custodian_private_ed25519_key', type=Path)
    p.add_argument('private_outcome_output', type=Path)
    p.add_argument('--custodian-tag', required=True)
    p = modes.add_parser('prepare')
    p.add_argument('witness_database', type=Path)
    p.add_argument('original_custody_request', type=Path)
    p.add_argument('private_custody_outcome', type=Path)
    p.add_argument('pinned_custodian_public_pem', type=Path)
    p.add_argument('trusted_custodian_pem_sha256')
    p.add_argument('private_reconciliation_request_output', type=Path)
    p.add_argument('--custodian-tag', required=True)
    p = modes.add_parser('approve')
    p.add_argument('private_reconciliation_request', type=Path)
    p.add_argument('admin_id')
    p.add_argument('private_admin_signing_key', type=Path)
    p.add_argument('private_admin_approval_output', type=Path)
    p = modes.add_parser('recover')
    p.add_argument('witness_database', type=Path)
    for field in ('original_custody_request', 'private_custody_outcome',
                  'private_reconciliation_request', 'private_approval_a',
                  'private_approval_b'):
        p.add_argument(field, type=Path)
    p.add_argument('pinned_custodian_public_pem', type=Path)
    p.add_argument('trusted_custodian_pem_sha256')
    for n in ('a', 'b'):
        p.add_argument('admin_'+n+'_id')
        p.add_argument('admin_'+n+'_public_pem', type=Path)
        p.add_argument('admin_'+n+'_trusted_pem_sha256')
    p.add_argument('--custodian-tag', required=True)
    args = parser.parse_args(argv)
    try:
        def raw(file, maximum):
            return _read_limited(_private_regular_file(file), maximum)
        if args.mode == 'attest':
            result = attest_applied(
                args.custodian_database,
                raw(args.original_custody_request, MAX_ORIGINAL_REQUEST),
                args.custodian_private_ed25519_key,
                args.private_outcome_output, custodian_tag=args.custodian_tag)
            report = {'custody_operation_observed_applied': True,
                      'result_kind': result}
        elif args.mode == 'prepare':
            prepare(
                args.witness_database,
                raw(args.original_custody_request, MAX_ORIGINAL_REQUEST),
                raw(args.private_custody_outcome, MAX_OUTCOME),
                args.pinned_custodian_public_pem,
                args.trusted_custodian_pem_sha256,
                args.private_reconciliation_request_output,
                custodian_tag=args.custodian_tag)
            report = {'private_reconciliation_prepared': True}
        elif args.mode == 'approve':
            approve(raw(args.private_reconciliation_request, MAX_REQUEST),
                    args.admin_id, args.private_admin_signing_key,
                    args.private_admin_approval_output)
            report = {'private_admin_approval_created': True}
        else:
            count = recover(
                args.witness_database,
                raw(args.original_custody_request, MAX_ORIGINAL_REQUEST),
                raw(args.private_custody_outcome, MAX_OUTCOME),
                raw(args.private_reconciliation_request, MAX_REQUEST),
                raw(args.private_approval_a, MAX_APPROVAL),
                raw(args.private_approval_b, MAX_APPROVAL),
                args.pinned_custodian_public_pem,
                args.trusted_custodian_pem_sha256,
                args.admin_a_id, args.admin_a_public_pem,
                args.admin_a_trusted_pem_sha256,
                args.admin_b_id, args.admin_b_public_pem,
                args.admin_b_trusted_pem_sha256,
                custodian_tag=args.custodian_tag)
            report = {'orphaned_applied_fence_retired': True,
                      'reconciliation_sequence': count}
        code = 0
    except ReconciliationConflict:
        report, code = {'fence_reconciliation_blocked': True}, 1
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            UnicodeError, sqlite3.Error, OverflowError):
        report, code = {'valid_input': False,
                        'error_code': 'invalid_private_reconciliation_input'}, 2
    report.update({
        'schema': REPORT_SCHEMA,
        'uncommitted_operations_automatically_released': False,
        'production_witness_deployed': False,
        'custodian_server_quiescence_proved': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_keys_or_tokens_emitted': False,
    })
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
