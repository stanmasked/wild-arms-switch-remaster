"""Stage-263 conservative, read-only preflight for an ambiguous custody write.

An externally signed supervisor statement is checked, and the original
custody request and independently fenced witness are re-examined while a
SQLite writer lock is held. A signed shutdown *claim* is not an OS proof:
this tool NEVER retires fences or authorizes abandonment. In particular a
future writer could resume after the preflight transaction closes.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_anchor_handoff import _history, GENESIS
    from .audit_record_capture_stream_binding import _digest, _read_limited
    from .audit_record_custodian_recovery import audit_history
    from .audit_record_custodian_reservation import reservation_row, token_hash
    from .audit_record_recovery_witness import _witness_rows
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence import _fence_row, _owner
    from .audit_record_witness_fence_reconciliation import (
        _audit, _original, _request_digest, _signed,
        ReconciliationConflict, MAX_ORIGINAL_REQUEST,
    )
    from .audit_record_signed_custodian import _tag
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import _history, GENESIS
    from audit_record_capture_stream_binding import _digest, _read_limited
    from audit_record_custodian_recovery import audit_history
    from audit_record_custodian_reservation import reservation_row, token_hash
    from audit_record_recovery_witness import _witness_rows
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence import _fence_row, _owner
    from audit_record_witness_fence_reconciliation import (
        _audit, _original, _request_digest, _signed,
        ReconciliationConflict, MAX_ORIGINAL_REQUEST,
    )
    from audit_record_signed_custodian import _tag

STOP_SCHEMA = 'wild-arms-ps1-witness-supervisor-stop-claim-v1'
STOP_DOMAIN = b'wild-arms-ps1-witness-supervisor-stop-claim-v1\x00'
REPORT_SCHEMA = 'wild-arms-ps1-witness-abort-preflight-report-v1'
MAX_STOP = 2048
STOP_FLAGS = (
    'process_tree_terminated', 'service_restart_blocked',
    'network_ingress_blocked', 'custody_writer_access_denied',
)
STOP_FIELDS = {
    'schema', 'supervisor_tag', 'custody_request_sha256',
    'fence_owner_sha256', 'stop_session_nonce',
    'process_identity_sha256', 'control_evidence_sha256',
    *STOP_FLAGS,
}


class PreflightConflict(ReconciliationConflict):
    """Negative snapshot or independent witness fence cannot be confirmed."""


def _verified_stop(original, signed_stop, supervisor_public, supervisor_pin,
                   supervisor_tag):
    request, _ = _original(original)
    body = _signed(signed_stop, STOP_SCHEMA, STOP_DOMAIN,
                   supervisor_pin, supervisor_public)
    if (set(body) != STOP_FIELDS
            or body['schema'] != STOP_SCHEMA
            or body['supervisor_tag'] != _tag(supervisor_tag)
            or body['custody_request_sha256'] != _request_digest(original)
            or body['fence_owner_sha256'] != _owner(request['request_id'])
            or type(body['stop_session_nonce']) is not str
            or len(body['stop_session_nonce']) != 32
            or any(c not in '0123456789abcdef'
                   for c in body['stop_session_nonce'])
            or any(body[key] is not True for key in STOP_FLAGS)):
        raise ValueError('untrusted or mismatched signed supervisor stop claim')
    _digest(body['process_identity_sha256'])
    _digest(body['control_evidence_sha256'])
    return body


def _negative_state(con, original):
    """Observe absence only within the held SQLite writer transaction."""
    request, _ = _original(original)
    history = _history(con)
    audit_history(con)
    reservation = reservation_row(con)
    if not history or (history[-1][0], history[-1][3]) != (
            request['expected_sequence'], request['expected_receipt_sha256']):
        raise PreflightConflict('custody head changed or cannot be authenticated')
    if request['action'] == 'reserve':
        if reservation is None:
            return 'reservation-not-observed-in-snapshot'
        # A previously committed *different* reservation is harmless only
        # when it formed the current custody head. Never clear that row.
        if (reservation[4] == 'committed'
                and reservation[1] + 1 == history[-1][0]
                and reservation[5] == history[-1][1]
                and reservation[3] != token_hash(request['reservation_token'])):
            return 'reservation-not-observed-in-snapshot'
        raise PreflightConflict('reservation already applied or disputed')
    if (reservation is None or
            (reservation[1], reservation[2], reservation[3], reservation[4]) != (
                request['expected_sequence'],
                request['expected_receipt_sha256'],
                token_hash(request['reservation_token']), 'reserved')):
        raise PreflightConflict('missing or changed reservation for uncommitted deposit')
    return 'checkpoint-not-committed-in-snapshot'


def preflight(witness_db, custodian_db, original_raw, signed_stop_raw,
              supervisor_public, supervisor_pin, *, supervisor_tag):
    """Check signed claims and point-in-time negative evidence. NEVER release."""
    req, _ = _original(original_raw)
    _verified_stop(original_raw, signed_stop_raw, supervisor_public,
                   supervisor_pin, supervisor_tag)
    # Hold the custody writer lock during the witness comparison. It
    # serializes SQLite writers only for this short read window; it does
    # NOT stop an idle or restarted writer after transaction completion.
    with closing(_connect(custodian_db)) as custody:
        custody.execute('BEGIN IMMEDIATE')
        try:
            classification = _negative_state(custody, original_raw)
            with closing(_connect(witness_db)) as witness:
                witness.execute('BEGIN IMMEDIATE')
                try:
                    rows = _witness_rows(witness)
                    _audit(witness)
                    fence = _fence_row(witness)
                    head = (len(rows), rows[-1][4] if rows else GENESIS)
                    if (fence is None or
                            (fence[1], fence[2]) != (
                                _owner(req['request_id']),
                                _request_digest(original_raw)) or
                            (fence[3], fence[4]) != head):
                        raise PreflightConflict('independent witness fence differs')
                    witness.rollback()  # This command has no write capability.
            custody.rollback()
        except Exception:
            custody.rollback()
            raise
    return {
        'schema': REPORT_SCHEMA,
        'negative_snapshot_classification': classification,
        'signed_external_stop_claim_verified': True,
        'negative_state_observed_under_sqlite_writer_lock': True,
        'external_process_quiescence_independently_proved': False,
        'all_writer_entrypoints_durably_disabled': False,
        'fence_retirement_authorized': False,
        'fence_retired': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_tokens_or_keys_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('witness_database', type=Path)
    parser.add_argument('custodian_database', type=Path)
    parser.add_argument('original_private_request', type=Path)
    parser.add_argument('signed_supervisor_stop_claim', type=Path)
    parser.add_argument('pinned_supervisor_public_pem', type=Path)
    parser.add_argument('trusted_supervisor_pem_sha256')
    parser.add_argument('--supervisor-tag', required=True)
    args = parser.parse_args(argv)
    try:
        report = preflight(
            args.witness_database, args.custodian_database,
            _read_limited(_private_regular_file(args.original_private_request),
                          MAX_ORIGINAL_REQUEST),
            _read_limited(_private_regular_file(args.signed_supervisor_stop_claim),
                          MAX_STOP),
            args.pinned_supervisor_public_pem,
            args.trusted_supervisor_pem_sha256,
            supervisor_tag=args.supervisor_tag)
        code = 0
    except PreflightConflict:
        report, code = {'schema': REPORT_SCHEMA,
                        'abort_preflight_blocked': True,
                        'fence_retired': False}, 1
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            UnicodeError, sqlite3.Error, OverflowError):
        report, code = {'schema': REPORT_SCHEMA,
                        'valid_input': False, 'fence_retired': False}, 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
