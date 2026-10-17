"""Ed25519-signed private custodian receipts with pinned verifier public keys.

Uses the system OpenSSL Ed25519 implementation, not a home-grown primitive.
The signing key belongs ONLY to an independently operated custodian; the
verifier pins the SHA-256 of a provisioned PEM public key out of band.
This is an opt-in wrapper around the stage-249 one-operation receipt gate.
No network, TLS, key distribution or independent custodian is deployed here.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import subprocess
import tempfile

try:
    from .audit_record_anchor_handoff import (
        _read_latest, _receipt, _canonical,
    )
    from .audit_record_receipt_gated_admission import (
        bootstrap as base_bootstrap, issue as base_issue,
        accept as base_accept, acknowledge as base_ack,
        PendingHandoff, AnchorConflict,
    )
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _write_new_private,
    )
    from .audit_record_capture_stream_binding import (
        _read_limited, _parse, _digest, MAX_MANIFEST_BYTES, MAX_STREAM_BYTES,
    )
    from .audit_record_capture_provenance import MAX_PROVENANCE_BYTES, MAX_RECEIPT_BYTES
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from .audit_record_global_slot_witness import read_raw_iso_entry
except ImportError:
    from audit_record_anchor_handoff import _read_latest, _receipt, _canonical
    from audit_record_receipt_gated_admission import (
        bootstrap as base_bootstrap, issue as base_issue,
        accept as base_accept, acknowledge as base_ack,
        PendingHandoff, AnchorConflict,
    )
    from audit_record_verifier_checkpoint import _private_regular_file, _write_new_private
    from audit_record_capture_stream_binding import (
        _read_limited, _parse, _digest, MAX_MANIFEST_BYTES, MAX_STREAM_BYTES,
    )
    from audit_record_capture_provenance import MAX_PROVENANCE_BYTES, MAX_RECEIPT_BYTES
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from audit_record_global_slot_witness import read_raw_iso_entry

ENVELOPE_SCHEMA = 'wild-arms-ps1-ed25519-custodian-receipt-v1'
REPORT_SCHEMA = 'wild-arms-ps1-ed25519-custodian-audit-v1'
SIGNED_CONTEXT = b'wild-arms-ps1-custodian-receipt-ed25519-v1\x00'
MAX_SIGNED_BYTES = 4096
MAX_PEM_BYTES = 4096
_TAG = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}\Z')
_HEXSIG = re.compile(r'[0-9a-f]{128}\Z')
_RECEIPT_KEYS = {
    'schema', 'sequence', 'checkpoint_sha256', 'previous_receipt_sha256',
}


def _tag(value):
    if type(value) is not str or not _TAG.fullmatch(value):
        raise ValueError('invalid custodian identity')
    return value


def _signed_bytes(body):
    return SIGNED_CONTEXT + _canonical(body)


def _openssl(key_path, raw_message, *, signature=None):
    """Sign or verify private local payload without exposing subprocess logs."""
    with tempfile.TemporaryDirectory(prefix='wa-custodian-ed25519-') as temp:
        base = Path(temp)
        msg = base / 'payload.bin'
        msg.write_bytes(raw_message)
        signature_path = base / 'signature.bin'
        if signature is not None:
            signature_path.write_bytes(signature)
        command = ['openssl', 'pkeyutl']
        if signature is None:
            command.extend(['-sign', '-inkey', str(key_path)])
        else:
            command.extend(['-verify', '-pubin', '-inkey', str(key_path)])
        command.extend(['-rawin', '-in', str(msg)])
        if signature is None:
            command.extend(['-out', str(signature_path)])
        else:
            command.extend(['-sigfile', str(signature_path)])
        try:
            result = subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('unavailable local Ed25519 crypto provider') from exc
        if signature is None:
            if result.returncode != 0:
                raise ValueError('custodian signing failed')
            raw = signature_path.read_bytes()
            if len(raw) != 64:
                raise ValueError('invalid Ed25519 signature length')
            return raw
        return result.returncode == 0


def sign_latest(custodian_db, private_signing_key, private_output, *, custodian_tag):
    """Sign ONLY a custody-committed latest receipt with private Ed25519 key."""
    custodian_tag = _tag(custodian_tag)
    key_path = _private_regular_file(private_signing_key)
    if key_path.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('oversized private signing key')
    row = _read_latest(custodian_db)
    body = {
        'schema': ENVELOPE_SCHEMA,
        'custodian_tag': custodian_tag,
        'receipt': _receipt(row[0], row[1], row[2]),
    }
    raw_signature = _openssl(key_path, _signed_bytes(body))
    envelope = {**body, 'signature_hex': raw_signature.hex()}
    raw = _canonical(envelope)
    if len(raw) > MAX_SIGNED_BYTES:
        raise ValueError('signed receipt too large')
    _write_new_private(private_output, raw)
    return row[0]


def verify_signed(raw_envelope, pinned_public_key, expected_public_key_sha256,
                  *, custodian_tag):
    """Return stage-248 receipt bytes only when signature AND external pin match.

    expected_public_key_sha256 MUST come from an independent trusted setting;
    deriving it on the fly from untrusted PEM would defeat key pinning.
    """
    tag = _tag(custodian_tag)
    _digest(expected_public_key_sha256)
    if (type(raw_envelope) is not bytes or
            not 0 < len(raw_envelope) <= MAX_SIGNED_BYTES):
        raise ValueError('invalid bounded signed receipt')
    obj = _parse(raw_envelope)
    if (type(obj) is not dict or set(obj) != {
            'schema', 'custodian_tag', 'receipt', 'signature_hex'}
            or obj['schema'] != ENVELOPE_SCHEMA
            or obj['custodian_tag'] != tag):
        raise ValueError('invalid signed custodian envelope')
    hexsig = obj['signature_hex']
    if type(hexsig) is not str or not _HEXSIG.fullmatch(hexsig):
        raise ValueError('invalid bounded Ed25519 signature')
    receipt = obj['receipt']
    if (type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS
            or receipt['schema'] != 'wild-arms-ps1-custodian-handoff-receipt-v1'
            or type(receipt['sequence']) is not int
            or receipt['sequence'] < 1):
        raise ValueError('invalid signed custodian receipt fields')
    _digest(receipt['checkpoint_sha256'])
    _digest(receipt['previous_receipt_sha256'])
    key_path = _private_regular_file(pinned_public_key)
    pub_raw = _read_limited(key_path, MAX_PEM_BYTES)
    if not hmac.compare_digest(hashlib.sha256(pub_raw).hexdigest(),
                               expected_public_key_sha256):
        raise ValueError('trusted custodian public key pin mismatch')
    body = {key: obj[key] for key in ('schema', 'custodian_tag', 'receipt')}
    if not _openssl(key_path, _signed_bytes(body),
                    signature=bytes.fromhex(hexsig)):
        raise ValueError('invalid custodian Ed25519 signature')
    return _canonical(receipt)


def _receipt_arg(args):
    signed = _read_limited(_private_regular_file(args.signed_receipt),
                           MAX_SIGNED_BYTES)
    return verify_signed(signed, args.pinned_public_key,
                         args.expected_public_key_sha256,
                         custodian_tag=args.custodian_tag)


def _report(**state):
    return {
        'schema': REPORT_SCHEMA,
        **state,
        'pinned_custodian_ed25519_receipt_checked': True,
        'independent_custodian_operated_and_authenticated': False,
        'network_transport_authentication_provided': False,
        'cross_database_atomic_commit_guaranteed': False,
        'external_rollback_protection_guaranteed': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_nonces_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    sign = sub.add_parser('sign')
    sign.add_argument('custodian_database', type=Path)
    sign.add_argument('private_signing_key', type=Path)
    sign.add_argument('private_signed_receipt_output', type=Path)
    sign.add_argument('--custodian-tag', required=True)
    for name in ('verify', 'bootstrap', 'issue', 'ack', 'accept'):
        p = sub.add_parser(name)
        if name == 'verify':
            p.add_argument('signed_receipt', type=Path)
        else:
            p.add_argument('verifier_database', type=Path)
            p.add_argument('custodian_database', type=Path)
            p.add_argument('signed_receipt', type=Path)
        p.add_argument('pinned_public_key', type=Path)
        p.add_argument('expected_public_key_sha256')
        p.add_argument('--custodian-tag', required=True)
        if name == 'issue':
            p.add_argument('--ttl-seconds', type=int, default=300)
        elif name == 'accept':
            for field in ('disc', 'inventory', 'temporal_claim', 'binding_manifest',
                          'before_stream', 'after_stream', 'provenance',
                          'before_receipt', 'after_receipt'):
                p.add_argument(field, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'sign':
            seq = sign_latest(args.custodian_database, args.private_signing_key,
                              args.private_signed_receipt_output,
                              custodian_tag=args.custodian_tag)
            result, code = _report(signed_receipt_written_privately=True,
                                   custody_sequence=seq,
                                   pinned_custodian_ed25519_receipt_checked=False), 0
        else:
            receipt = _receipt_arg(args)
            if args.mode == 'verify':
                result, code = _report(signature_and_public_key_pin_valid=True), 0
            elif args.mode == 'bootstrap':
                base_bootstrap(args.verifier_database, args.custodian_database,
                               receipt)
                result, code = _report(bootstrap_committed=True), 0
            elif args.mode == 'issue':
                nonce = base_issue(args.verifier_database, args.custodian_database,
                                   receipt, ttl_seconds=args.ttl_seconds)
                # Only issuing exposes a fresh nonce for PRIVATE delivery.
                print(json.dumps({
                    'schema': REPORT_SCHEMA, 'issued_private_session_nonce': nonce,
                    'pending_custodian_acknowledgment': True,
                    'pinned_custodian_ed25519_receipt_checked': True,
                    'independent_custodian_operated_and_authenticated': False,
                }, sort_keys=True))
                return 0
            elif args.mode == 'ack':
                changed = base_ack(args.verifier_database, args.custodian_database,
                                   receipt)
                result, code = _report(acknowledgment_recorded=changed,
                                       already_acknowledged=not changed), 0
            else:
                entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
                matches = [row for row in entries if type(row) is dict
                           and row.get('path') == '/EXE/WILDARMS.EXE;1'
                           and not row.get('directory', False)]
                if len(matches) != 1:
                    raise ValueError('missing private EXE inventory')
                data = (
                    read_raw_iso_entry(args.disc, matches[0]),
                    _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
                    _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
                    _read_limited(args.before_stream, MAX_STREAM_BYTES),
                    _read_limited(args.after_stream, MAX_STREAM_BYTES),
                    _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
                    _read_limited(args.before_receipt, MAX_RECEIPT_BYTES),
                    _read_limited(args.after_receipt, MAX_RECEIPT_BYTES),
                )
                accepted = base_accept(args.verifier_database, args.custodian_database,
                                       receipt, *data)
                result, code = _report(accepted_with_pending_anchor=accepted), (
                    0 if accepted else 1)
    except (PendingHandoff, AnchorConflict):
        result, code = _report(further_admission_blocked=True), 1
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, IndexError,
            OverflowError, RecursionError):
        result, code = {
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_nonces_or_values_emitted': False,
        }, 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
