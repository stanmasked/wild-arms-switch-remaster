"""Reserved capture acceptance with durable purpose-bound reservation intent."""
from contextlib import closing
import hashlib

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES)
    from .audit_record_capture_stream_binding import _sha
    from .audit_record_guarded_admission import _now
    from .audit_record_receipt_gated_admission import _ready, accept_with_latest, AnchorConflict
    from .audit_record_remote_admission import _remote_head
    from .audit_record_remote_reserved_issue import _prepare
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES)
    from audit_record_capture_stream_binding import _sha
    from audit_record_guarded_admission import _now
    from audit_record_receipt_gated_admission import _ready, accept_with_latest, AnchorConflict
    from audit_record_remote_admission import _remote_head
    from audit_record_remote_reserved_issue import _prepare


def evidence_digest(evidence):
    """Bind a reserved head to the exact eight length-delimited byte fields."""
    if len(evidence) != 8 or any(not isinstance(value, (bytes, bytearray)) for value in evidence):
        raise ValueError('invalid evidence bundle')
    checksum = hashlib.sha256(b'wild-arms-reserved-accept-evidence-v1\x00')
    for item in evidence:
        checksum.update(len(item).to_bytes(8, 'big'))
        checksum.update(bytes(item))
    return checksum.hexdigest()


def eligible(db_path, latest, evidence, *, now=None):
    """Check original evidence and nonce eligibility before remote reserve."""
    exe, temporal, binding, before, after, provenance, before_receipt, after_receipt = evidence
    report = audit_provenance(
        exe, temporal, binding, before, after, provenance, before_receipt, after_receipt)
    if not report['all_supplied_provenance_claims_consistent']:
        return False
    nonce = _json_object(provenance, MAX_PROVENANCE_BYTES)['session_nonce']
    timestamp = _now(now)
    before_digest, after_digest = _sha(before), _sha(after)
    if before_digest == after_digest:
        raise ValueError('identical capture stream digests')
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            _ready(con, latest)
            challenge = con.execute(
                'SELECT issued_at, expires_at, consumed FROM challenges'
                ' WHERE nonce=?', (nonce,)).fetchone()
            valid = (
                challenge is not None and not challenge[2]
                and challenge[0] <= timestamp < challenge[1]
                and con.execute(
                    'SELECT 1 FROM accepted_streams WHERE sha256 IN (?,?) LIMIT 1',
                    (before_digest, after_digest)).fetchone() is None
                and con.execute(
                    'SELECT 1 FROM accepted WHERE provenance_sha256=? LIMIT 1',
                    (_sha(provenance),)).fetchone() is None)
            con.commit()
            return bool(valid)
        except Exception:
            con.rollback()
            raise


def accept_reserved(db_path, transport, public_key, pinned_sha256,
                    *evidence, tag, now=None):
    """Fail closed before reservation; preserve intent on network failure."""
    digest = evidence_digest(evidence)
    current = _remote_head(transport, public_key, pinned_sha256, tag=tag)
    if not eligible(db_path, current, evidence, now=now):
        return False
    token = _prepare(
        db_path, current, purpose='accept', evidence_sha256=digest)
    reserved = _remote_head(
        transport, public_key, pinned_sha256, tag=tag, action='reserve',
        expected_sequence=current[0], expected_receipt_sha256=current[3],
        reservation_token=token)
    if (reserved[0] != current[0] or reserved[3] != current[3]
            or reserved[1] != current[1]):
        raise AnchorConflict('reserved custody head changed unexpectedly')
    return accept_with_latest(db_path, current, *evidence, now=now)


def main(argv=None):
    """Private CLI for reserved acceptance and recoverable acknowledgment."""
    import argparse
    import json
    from pathlib import Path
    import sqlite3
    import ssl
    try:
        from .audit_record_capture_stream_binding import (
            _read_limited, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES)
        from .audit_record_capture_provenance import MAX_RECEIPT_BYTES
        from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
        from .audit_record_global_slot_witness import read_raw_iso_entry
        from .audit_record_remote_admission import _transport
        from .audit_record_remote_reserved_issue import acknowledge_reserved
        from .audit_record_receipt_gated_admission import (
            PendingHandoff, AnchorConflict)
    except ImportError:
        from audit_record_capture_stream_binding import (
            _read_limited, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES)
        from audit_record_capture_provenance import MAX_RECEIPT_BYTES
        from audit_record_executed_access_claims import MAX_REFERENCE_BYTES
        from audit_record_global_slot_witness import read_raw_iso_entry
        from audit_record_remote_admission import _transport
        from audit_record_remote_reserved_issue import acknowledge_reserved
        from audit_record_receipt_gated_admission import PendingHandoff, AnchorConflict

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    for mode in ('accept', 'ack'):
        p = commands.add_parser(mode)
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
        if mode == 'accept':
            for name in ('disc', 'inventory', 'temporal_claim',
                         'binding_manifest', 'before_stream', 'after_stream',
                         'provenance', 'before_receipt', 'after_receipt'):
                p.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        transport = _transport(args)
        if args.mode == 'ack':
            changed = acknowledge_reserved(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256, tag=args.custodian_tag)
            result, status = {
                'reserved_acknowledgment_committed': changed,
                'already_acknowledged': not changed}, 0
        else:
            rows = json.loads(
                args.inventory.read_text(encoding='utf-8'))['entries']
            matches = [row for row in rows if type(row) is dict
                       and row.get('path') == '/EXE/WILDARMS.EXE;1'
                       and not row.get('directory', False)]
            if len(matches) != 1:
                raise ValueError('missing executable inventory entry')
            evidence = (
                read_raw_iso_entry(args.disc, matches[0]),
                _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
                _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
                _read_limited(args.before_stream, MAX_STREAM_BYTES),
                _read_limited(args.after_stream, MAX_STREAM_BYTES),
                _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
                _read_limited(args.before_receipt, MAX_RECEIPT_BYTES),
                _read_limited(args.after_receipt, MAX_RECEIPT_BYTES))
            accepted = accept_reserved(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256,
                *evidence, tag=args.custodian_tag)
            result, status = {
                'capture_accepted_pending_reserved_ack': accepted}, (
                    0 if accepted else 1)
    except (PendingHandoff, AnchorConflict):
        result, status = {'admission_blocked': True}, 1
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, sqlite3.Error, ssl.SSLError):
        result, status = {
            'valid_input': False,
            'error_code': 'invalid_private_input_or_custodian'}, 2
    result.update({
        'schema': 'wild-arms-ps1-reserved-capture-acceptance-v1',
        'requires_local_custodian_db': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'independent_custodian_deployed': False,
        'legacy_verifier_commands_disabled': False,
        'private_nonces_hashes_or_values_emitted': False,
    })
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
