"""Remote-only custody admission adapter with no verifier custody DB copy.

Stage-251 mutual TLS + pinned Ed25519 receipt are checked on every exchange.
Stage-249 admission transactions accept the authenticated remote custody head;
local issue/accept commit durable pending handoff before any network deposit.
Ack submits the exact locally pending checkpoint, then verifies custody and
clears pending only after the remote signed confirmation succeeds.

This is opt-in; legacy unguarded interfaces still exist. Remote high-water
freshness between fetch and local commit requires an exclusive custodian
writer/deployment policy; distributed atomicity is not provided.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import ssl

try:
    from .audit_record_anchor_handoff import _receipt_hash, _canonical
    from .audit_record_atomic_verifier import _connect
    from .audit_record_capture_stream_binding import (
        _read_limited, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from .audit_record_capture_provenance import (
        MAX_PROVENANCE_BYTES, MAX_RECEIPT_BYTES,
    )
    from .audit_record_custodian_tls import exchange
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_receipt_gated_admission import (
        bootstrap_with_latest, issue_with_latest, accept_with_latest,
        acknowledge_with_latest, _guard, _checkpoint_digest,
        PendingHandoff, AnchorConflict,
    )
    from .audit_record_signed_custodian import verify_signed
    from .audit_record_verifier_checkpoint import _snapshot_from_connection, _validate_checkpoint
except ImportError:
    from audit_record_anchor_handoff import _receipt_hash, _canonical
    from audit_record_atomic_verifier import _connect
    from audit_record_capture_stream_binding import _read_limited, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES
    from audit_record_capture_provenance import MAX_PROVENANCE_BYTES, MAX_RECEIPT_BYTES
    from audit_record_custodian_tls import exchange
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_receipt_gated_admission import (
        bootstrap_with_latest, issue_with_latest, accept_with_latest,
        acknowledge_with_latest, _guard, _checkpoint_digest,
        PendingHandoff, AnchorConflict,
    )
    from audit_record_signed_custodian import verify_signed
    from audit_record_verifier_checkpoint import _snapshot_from_connection, _validate_checkpoint

REPORT_SCHEMA = 'wild-arms-ps1-remote-receipt-gated-admission-v1'


def _remote_head(transport, public_key, pinned_sha256, *, tag,
                 action='latest', checkpoint_raw=None,
                 expected_sequence=None, expected_receipt_sha256=None):
    """Return a custody row compatible with stage 249 from a signed TLS reply."""
    checkpoint, envelope, sequence = transport(
        action=action, checkpoint_raw=checkpoint_raw,
        expected_sequence=expected_sequence,
        expected_receipt_sha256=expected_receipt_sha256)
    if type(sequence) is not int or sequence < 1:
        raise ValueError('invalid custodian sequence')
    _validate_checkpoint(checkpoint)
    private_receipt = verify_signed(
        envelope, public_key, pinned_sha256, custodian_tag=tag)
    from_json = json.loads(private_receipt)
    digest = _sha(checkpoint)
    if (from_json['sequence'] != sequence
            or from_json['checkpoint_sha256'] != digest):
        raise AnchorConflict('remote receipt and checkpoint disagree')
    # Same positional shape as stage-248 _read_latest, but obtained entirely
    # from a signature-verified network response (no local custody SQLite).
    return (sequence, digest, from_json['previous_receipt_sha256'],
            _receipt_hash(from_json), checkpoint)


def bootstrap_remote(db_path, transport, public_key, pinned_sha256, *, tag):
    latest = _remote_head(transport, public_key, pinned_sha256, tag=tag)
    return bootstrap_with_latest(db_path, latest)


def issue_remote(db_path, transport, public_key, pinned_sha256, *, tag,
                 ttl_seconds=300, now=None):
    latest = _remote_head(transport, public_key, pinned_sha256, tag=tag)
    return issue_with_latest(db_path, latest, ttl_seconds=ttl_seconds, now=now)


def accept_remote(db_path, transport, public_key, pinned_sha256, *evidence,
                  tag, now=None):
    latest = _remote_head(transport, public_key, pinned_sha256, tag=tag)
    return accept_with_latest(db_path, latest, *evidence, now=now)


def _pending_state(db_path):
    """Snapshot pending data atomically; do not mutate on failed network."""
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN')
        try:
            seq, acknowledged_hash, pending_seq, pending_hash = _guard(con)
            if pending_seq is None:
                con.commit()
                return None
            raw = _canonical(_snapshot_from_connection(con))
            if (_sha(raw) != pending_hash or pending_seq != seq + 1):
                raise AnchorConflict('pending checkpoint was changed')
            con.commit()
            return raw, seq, acknowledged_hash
        except Exception:
            con.rollback()
            raise


def acknowledge_remote(db_path, transport, public_key, pinned_sha256, *, tag):
    """Network loss leaves local pending unchanged; repeat is safe.

    A pending operation is submitted via stage-248's idempotent deposit.
    An already-acknowledged operation uses read-only latest to recover
    from lost acknowledgment replies without submitting another round.
    """
    pending = _pending_state(db_path)
    latest = _remote_head(
        transport, public_key, pinned_sha256, tag=tag,
        action='deposit' if pending is not None else 'latest',
        checkpoint_raw=pending[0] if pending is not None else None,
        expected_sequence=pending[1] if pending is not None else None,
        expected_receipt_sha256=pending[2] if pending is not None else None)
    return acknowledge_with_latest(db_path, latest)


def _transport(args):
    def invoke(*, action, checkpoint_raw, expected_sequence=None,
               expected_receipt_sha256=None):
        return exchange(
            args.host, args.port, hostname=args.tls_hostname,
            cert=args.tls_client_cert, key=args.tls_client_key,
            ca=args.trusted_server_ca,
            server_cert_sha256=args.server_leaf_der_sha256,
            pinned_signing_public_key=args.pinned_custodian_ed25519_public_key,
            signing_public_key_sha256=args.custodian_ed25519_public_pem_sha256,
            tag=args.custodian_tag, action=action, checkpoint_raw=checkpoint_raw,
            expected_sequence=expected_sequence,
            expected_receipt_sha256=expected_receipt_sha256)
    return invoke


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    for mode in ('bootstrap', 'issue', 'accept', 'ack'):
        p = sub.add_parser(mode)
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
        if mode == 'issue':
            p.add_argument('--ttl-seconds', type=int, default=300)
        if mode == 'accept':
            for field in ('disc', 'inventory', 'temporal_claim', 'binding_manifest',
                          'before_stream', 'after_stream', 'provenance',
                          'before_receipt', 'after_receipt'):
                p.add_argument(field, type=Path)
    args = parser.parse_args(argv)
    try:
        transport = _transport(args)
        if args.operation == 'bootstrap':
            bootstrap_remote(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256,
                tag=args.custodian_tag)
            result, status = {'remote_bootstrap_committed': True}, 0
        elif args.operation == 'issue':
            nonce = issue_remote(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256,
                tag=args.custodian_tag, ttl_seconds=args.ttl_seconds)
            print(json.dumps({
                'schema': REPORT_SCHEMA,
                'private_newly_issued_nonce': nonce,
                'remote_acknowledgment_pending': True,
                'private_existing_nonces_or_hashes_emitted': False,
            }, sort_keys=True))
            return 0
        elif args.operation == 'ack':
            changed = acknowledge_remote(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256,
                tag=args.custodian_tag)
            result, status = {
                'remote_custodian_acknowledged': changed,
                'idempotent_already_acknowledged': not changed}, 0
        else:
            inventory = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
            entries = [r for r in inventory if type(r) is dict
                       and r.get('path') == '/EXE/WILDARMS.EXE;1'
                       and not r.get('directory', False)]
            if len(entries) != 1:
                raise ValueError('missing original EXE inventory')
            data = (
                read_raw_iso_entry(args.disc, entries[0]),
                _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
                _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
                _read_limited(args.before_stream, MAX_STREAM_BYTES),
                _read_limited(args.after_stream, MAX_STREAM_BYTES),
                _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
                _read_limited(args.before_receipt, MAX_RECEIPT_BYTES),
                _read_limited(args.after_receipt, MAX_RECEIPT_BYTES))
            accepted = accept_remote(
                args.verifier_database, transport,
                args.pinned_custodian_ed25519_public_key,
                args.custodian_ed25519_public_pem_sha256,
                *data, tag=args.custodian_tag)
            result, status = {'capture_accepted_pending_remote_anchor': accepted}, (
                0 if accepted else 1)
    except (PendingHandoff, AnchorConflict):
        result, status = {'admission_or_acknowledgment_blocked': True}, 1
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError,
            ssl.SSLError, sqlite3.Error):
        result, status = {'valid_input': False,
                          'error_code': 'invalid_private_input_or_remote_custodian'}, 2
    result.update({
        'schema': REPORT_SCHEMA,
        'remote_signed_tls_custodian_used': status == 0,
        'verifier_requires_local_custodian_db': False,
        'custodian_independently_provisioned': False,
        'global_external_rollback_prevention_guaranteed': False,
        'cross_database_atomic_commit_guaranteed': False,
        'legacy_admission_interfaces_also_protected': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_existing_nonces_or_hashes_emitted': False,
    })
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
