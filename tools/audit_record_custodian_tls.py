"""One-request mutual-TLS 1.3 reference custodian transport (stage 251).

The channel authenticates both TLS peers through independently provisioned
CA roots AND SHA256 pins of exact peer DER leaf certificates. Checkpoints
are only processed by the stage-248 monotonic SQLite custodian, while the
reply is independently Ed25519-signed as in stage 250. No remote service is
provisioned by this repository; key ownership and pins are external.
"""
import argparse
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import socket
import ssl
import struct
import sys

try:
    from .audit_record_anchor_handoff import (
        deposit, _read_latest, _receipt, _receipt_hash, _canonical, HandoffRegression,
    )
    from .audit_record_signed_custodian import (
        ENVELOPE_SCHEMA, _signed_bytes, _openssl, _tag, MAX_PEM_BYTES,
        MAX_SIGNED_BYTES, verify_signed,
    )
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _validate_checkpoint, _write_new_private,
        MAX_CHECKPOINT_BYTES,
    )
    from .audit_record_capture_stream_binding import (
        _read_limited, _parse, _digest, _sha,
    )
    from .audit_record_custodian_reservation import reserve, token_hash
except ImportError:
    from audit_record_anchor_handoff import (
        deposit, _read_latest, _receipt, _receipt_hash, _canonical, HandoffRegression,
    )
    from audit_record_signed_custodian import (
        ENVELOPE_SCHEMA, _signed_bytes, _openssl, _tag, MAX_PEM_BYTES,
        MAX_SIGNED_BYTES, verify_signed,
    )
    from audit_record_verifier_checkpoint import (
        _private_regular_file, _validate_checkpoint, _write_new_private,
        MAX_CHECKPOINT_BYTES,
    )
    from audit_record_capture_stream_binding import (
        _read_limited, _parse, _digest, _sha,
    )
    from audit_record_custodian_reservation import reserve, token_hash

REQUEST_SCHEMA = 'wild-arms-ps1-mutual-tls-custodian-request-v1'
RESPONSE_SCHEMA = 'wild-arms-ps1-mutual-tls-custodian-response-v1'
REPORT_SCHEMA = 'wild-arms-ps1-mutual-tls-custodian-audit-v1'
MAX_FRAME = 1024 * 1024
SOCKET_TIMEOUT = 8


def _tls_context(cert, key, ca, *, server):
    for path in (cert, key, ca):
        path = _private_regular_file(path)
        if path.stat().st_size > 16384:
            raise ValueError('invalid TLS credential')
    ctx = ssl.create_default_context(
        ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH,
        cafile=str(ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_mode = ssl.CERT_REQUIRED
    if server:
        ctx.check_hostname = False
    else:
        ctx.check_hostname = True
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return ctx


def _peer_pin(tls_sock, expected_fingerprint):
    _digest(expected_fingerprint)
    der = tls_sock.getpeercert(binary_form=True)
    if not der or not hmac.compare_digest(
            hashlib.sha256(der).hexdigest(), expected_fingerprint):
        raise ValueError('unexpected authenticated TLS peer certificate')


def _read_exact(sock, amount):
    chunks = []
    while amount:
        chunk = sock.recv(amount)
        if not chunk:
            raise ValueError('truncated authenticated TLS frame')
        chunks.append(chunk)
        amount -= len(chunk)
    return b''.join(chunks)


def _receive(sock):
    length = struct.unpack('!I', _read_exact(sock, 4))[0]
    if not 0 < length <= MAX_FRAME:
        raise ValueError('invalid bounded TLS frame')
    return _parse(_read_exact(sock, length))


def _send(sock, value):
    raw = _canonical(value)
    if not 0 < len(raw) <= MAX_FRAME:
        raise ValueError('oversized TLS response')
    sock.sendall(struct.pack('!I', len(raw)) + raw)


def _b64_decode(value, limit):
    if type(value) is not str or len(value) > (limit + 2) * 4 // 3 + 8:
        raise ValueError('invalid bounded checkpoint encoding')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError('invalid base64 checkpoint') from exc
    if not 0 < len(raw) <= limit or base64.b64encode(raw).decode('ascii') != value:
        raise ValueError('noncanonical or oversized checkpoint')
    return raw


def _signed_latest(custodian_db, signing_key, tag):
    """Sign the exact currently committed custodian ledger head."""
    signer = _private_regular_file(signing_key)
    if signer.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('invalid private Ed25519 key')
    row = _read_latest(custodian_db)
    body = {
        'schema': ENVELOPE_SCHEMA,
        'custodian_tag': _tag(tag),
        'receipt': _receipt(row[0], row[1], row[2]),
    }
    envelope = {**body, 'signature_hex': _openssl(
        signer, _signed_bytes(body)).hex()}
    data = _canonical(envelope)
    if len(data) > MAX_SIGNED_BYTES:
        raise ValueError('oversized signed receipt')
    return row, data


def _process(request, custodian_db, signing_key, tag, *, witness_head=None):
    if (type(request) is not dict
            or request.get('schema') != REQUEST_SCHEMA
            or request.get('action') not in (
                'latest', 'deposit', 'reserve', 'deposit-reserved')
            or type(request.get('request_id')) is not str
            or len(request['request_id']) != 32
            or any(x not in '0123456789abcdef' for x in request['request_id'])):
        raise ValueError('invalid authenticated custody request')
    action = request['action']
    expected_keys = {'schema', 'action', 'request_id'}
    if action in ('reserve', 'deposit', 'deposit-reserved'):
        expected_keys.update({'expected_sequence', 'expected_receipt_sha256'})
    if action in ('deposit', 'deposit-reserved'):
        expected_keys.add('checkpoint_b64')
    if action in ('reserve', 'deposit-reserved'):
        expected_keys.add('reservation_token')
    if set(request) != expected_keys:
        raise ValueError('unexpected authenticated request fields')
    if action == 'reserve':
        reserve(
            custodian_db, request['expected_sequence'],
            request['expected_receipt_sha256'], request['reservation_token'],
            witness_head=witness_head)
    elif action in ('deposit', 'deposit-reserved'):
        offered = _b64_decode(request['checkpoint_b64'], MAX_CHECKPOINT_BYTES)
        _validate_checkpoint(offered)
        deposit(
            custodian_db, offered,
            expected_sequence=request['expected_sequence'],
            expected_receipt_sha256=request['expected_receipt_sha256'],
            reservation_token=(request['reservation_token']
                               if action == 'deposit-reserved' else None),
            witness_head=witness_head)
    row, signed = _signed_latest(custodian_db, signing_key, tag)
    return {
        'schema': RESPONSE_SCHEMA,
        'request_id': request['request_id'],
        'status': 'ok',
        'checkpoint_b64': base64.b64encode(row[4]).decode('ascii'),
        'signed_receipt_b64': base64.b64encode(signed).decode('ascii'),
    }


def serve_one(listener, custodian_db, signing_key, cert, key, ca,
              expected_client_cert_sha256, *, tag, witness_head=None,
              remote_witness_provider=None, witness_fence_provider=None):
    """Handle exactly one mutual TLS connection; false for rejected request.

    The caller owns the bound/listening socket. Deliberate one-shot API:
    deployment needs process supervision, backpressure and network hardening.
    """
    if sum(v is not None for v in (
            witness_head, remote_witness_provider,
            witness_fence_provider)) > 1:
        raise ValueError('multiple witness admission sources are forbidden')
    ctx = _tls_context(cert, key, ca, server=True)
    _digest(expected_client_cert_sha256)
    with listener.accept()[0] as conn:
        conn.settimeout(SOCKET_TIMEOUT)
        try:
            with ctx.wrap_socket(conn, server_side=True) as tls:
                _peer_pin(tls, expected_client_cert_sha256)
                request = _receive(tls)
                try:
                    head = witness_head
                    if remote_witness_provider is not None and (
                            type(request) is dict and
                            request.get('action') in (
                                'reserve', 'deposit', 'deposit-reserved')):
                        # Obtain a fresh authenticated witness response after
                        # authenticating the custody client and its request.
                        # No witness DB is opened by this custodian process.
                        head = remote_witness_provider()
                        if head is None:
                            raise ValueError('remote witness did not respond')
                    modifying = (type(request) is dict
                                 and request.get('action') in (
                                     'reserve', 'deposit', 'deposit-reserved'))
                    if witness_fence_provider is not None and modifying:
                        with witness_fence_provider(request) as fenced_head:
                            if fenced_head is None:
                                raise ValueError('remote fence not acquired')
                            response = _process(
                                request, custodian_db, signing_key, tag,
                                witness_head=fenced_head)
                    elif head is None:
                        if remote_witness_provider is not None and modifying:
                            raise ValueError('required remote witness missing')
                        response = _process(request, custodian_db, signing_key, tag)
                    else:
                        response = _process(
                            request, custodian_db, signing_key, tag,
                            witness_head=head)
                except (OSError, ValueError, HandoffRegression, sqlite3.Error):
                    _send(tls, {
                        'schema': RESPONSE_SCHEMA,
                        'request_id': request.get('request_id')
                        if type(request) is dict and
                        type(request.get('request_id')) is str else '',
                        'status': 'rejected',
                    })
                    return False
                _send(tls, response)
                return True
        except (OSError, ValueError, ssl.SSLError, sqlite3.Error):
            return False


def exchange(host, port, *, hostname, cert, key, ca, server_cert_sha256,
             pinned_signing_public_key, signing_public_key_sha256,
             tag, action='latest', checkpoint_raw=None,
             expected_sequence=None, expected_receipt_sha256=None,
             reservation_token=None):
    """Mutually authenticated exchange; verify signed response before return."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid custodian TLS port')
    if type(hostname) is not str or not hostname:
        raise ValueError('missing expected TLS hostname')
    _tag(tag)
    ctx = _tls_context(cert, key, ca, server=False)
    _digest(server_cert_sha256)
    request_id = secrets.token_hex(16)
    request = {
        'schema': REQUEST_SCHEMA, 'action': action, 'request_id': request_id,
    }
    if action in ('reserve', 'deposit', 'deposit-reserved'):
        if (type(expected_sequence) is not int or expected_sequence < 1
                or type(expected_receipt_sha256) is not str):
            raise ValueError('expected authenticated previous custody head is required')
        _digest(expected_receipt_sha256)
        request['expected_sequence'] = expected_sequence
        request['expected_receipt_sha256'] = expected_receipt_sha256
        if action in ('deposit', 'deposit-reserved'):
            _validate_checkpoint(checkpoint_raw)
            request['checkpoint_b64'] = base64.b64encode(checkpoint_raw).decode('ascii')
        elif checkpoint_raw is not None:
            raise ValueError('unexpected checkpoint on reserve')
        if action in ('reserve', 'deposit-reserved'):
            token_hash(reservation_token)
            request['reservation_token'] = reservation_token
        elif reservation_token is not None:
            raise ValueError('unexpected reservation token')
    elif (action != 'latest' or checkpoint_raw is not None
          or expected_sequence is not None
          or expected_receipt_sha256 is not None
          or reservation_token is not None):
        raise ValueError('invalid custodian operation')
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT) as plain:
        plain.settimeout(SOCKET_TIMEOUT)
        with ctx.wrap_socket(plain, server_hostname=hostname) as tls:
            _peer_pin(tls, server_cert_sha256)  # before sending any checkpoint
            _send(tls, request)
            response = _receive(tls)
    if (type(response) is not dict or
            response.get('schema') != RESPONSE_SCHEMA or
            response.get('request_id') != request_id or
            response.get('status') != 'ok' or set(response) != {
                'schema', 'request_id', 'status', 'checkpoint_b64',
                'signed_receipt_b64'}):
        raise ValueError('invalid, replayed or refused authenticated reply')
    latest_checkpoint = _b64_decode(response['checkpoint_b64'],
                                    MAX_CHECKPOINT_BYTES)
    _validate_checkpoint(latest_checkpoint)
    signed = _b64_decode(response['signed_receipt_b64'], MAX_SIGNED_BYTES)
    receipt = _parse(verify_signed(
        signed, pinned_signing_public_key, signing_public_key_sha256,
        custodian_tag=tag))
    if _sha(latest_checkpoint) != receipt['checkpoint_sha256']:
        raise ValueError('signed custody reply not bound to returned checkpoint')
    if action in ('deposit', 'deposit-reserved'):
        # A distinct future round, even one containing the offered state,
        # is NOT an acknowledgment of this CAS request. Permit only the
        # single expected next sequence for both fresh commits and retries.
        if receipt['sequence'] != expected_sequence + 1:
            raise ValueError('custodian reply not at expected next sequence')
        if receipt['previous_receipt_sha256'] != expected_receipt_sha256:
            raise ValueError('custodian reply does not chain to expected head')
        if latest_checkpoint != checkpoint_raw:
            raise ValueError('custodian reply not for exact offered checkpoint')
    if action == 'reserve' and (
            receipt['sequence'] != expected_sequence
            or _receipt_hash(receipt) != expected_receipt_sha256):
        raise ValueError('custodian reserve returned an unexpected previous head')
    return latest_checkpoint, signed, receipt['sequence']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    for mode in ('serve-once', 'serve-once-witness-guarded',
                 'serve-once-remote-witness-guarded',
                 'serve-once-remote-witness-fenced'):
        server = sub.add_parser(mode, help='one authenticated custodian connection')
        server.add_argument('custodian_database', type=Path)
        server.add_argument('private_ed25519_signing_key', type=Path)
        server.add_argument('tls_server_cert', type=Path)
        server.add_argument('tls_server_key', type=Path)
        server.add_argument('trusted_client_ca', type=Path)
        server.add_argument('expected_client_certificate_der_sha256')
        server.add_argument('--custodian-tag', required=True)
        server.add_argument('--host', default='127.0.0.1')
        server.add_argument('--port', type=int, required=True)
        if mode in ('serve-once-remote-witness-guarded',
                    'serve-once-remote-witness-fenced'):
            server.add_argument('witness_host')
            server.add_argument('witness_port', type=int)
            server.add_argument('witness_tls_hostname')
            server.add_argument('witness_tls_client_cert', type=Path)
            server.add_argument('witness_tls_client_key', type=Path)
            server.add_argument('witness_trusted_server_ca', type=Path)
            server.add_argument('witness_server_leaf_der_sha256')
            server.add_argument('trusted_witness_public_pem', type=Path)
            server.add_argument('trusted_witness_public_pem_sha256')
            server.add_argument('--witness-tag', required=True)
        if mode == 'serve-once-witness-guarded':
            server.add_argument('independent_witness_database', type=Path)
            server.add_argument('current_signed_witness_receipt', type=Path)
            server.add_argument('trusted_witness_public_pem', type=Path)
            server.add_argument('trusted_witness_pem_sha256')
            server.add_argument('--witness-tag', required=True)
    for name in ('latest', 'deposit'):
        p = sub.add_parser(name)
        p.add_argument('host')
        p.add_argument('port', type=int)
        p.add_argument('tls_hostname')
        p.add_argument('tls_client_cert', type=Path)
        p.add_argument('tls_client_key', type=Path)
        p.add_argument('trusted_server_ca', type=Path)
        p.add_argument('server_certificate_der_sha256')
        p.add_argument('pinned_ed25519_custodian_public_key', type=Path)
        p.add_argument('custodian_signing_public_key_sha256')
        p.add_argument('private_signed_receipt_output', type=Path)
        p.add_argument('private_checkpoint_output', type=Path)
        p.add_argument('--custodian-tag', required=True)
        if name == 'deposit':
            p.add_argument('private_checkpoint_offer', type=Path)
            p.add_argument('--expected-sequence', type=int, required=True)
            p.add_argument('--expected-receipt-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation in ('serve-once', 'serve-once-witness-guarded',
                              'serve-once-remote-witness-guarded',
                              'serve-once-remote-witness-fenced'):
            if not 1 <= args.port <= 65535:
                raise ValueError('invalid listen port')
            witness_head = None
            remote_witness_provider = None
            witness_fence_provider = None
            if args.operation == 'serve-once-remote-witness-fenced':
                try:
                    from .audit_record_remote_witness_fence import fenced_custody_request
                except ImportError:
                    from audit_record_remote_witness_fence import fenced_custody_request
                def witness_fence_provider(request):
                    return fenced_custody_request(
                        request, witness_host=args.witness_host,
                        witness_port=args.witness_port,
                        hostname=args.witness_tls_hostname,
                        cert=args.witness_tls_client_cert,
                        key=args.witness_tls_client_key,
                        ca=args.witness_trusted_server_ca,
                        server_pin=args.witness_server_leaf_der_sha256,
                        public_key=args.trusted_witness_public_pem,
                        public_pin=args.trusted_witness_public_pem_sha256,
                        tag=args.witness_tag)
            if args.operation == 'serve-once-remote-witness-guarded':
                try:
                    from .audit_record_remote_recovery_witness import fetch_head
                except ImportError:
                    from audit_record_remote_recovery_witness import fetch_head
                def remote_witness_provider():
                    return fetch_head(
                        args.witness_host, args.witness_port,
                        hostname=args.witness_tls_hostname,
                        cert=args.witness_tls_client_cert,
                        key=args.witness_tls_client_key,
                        ca=args.witness_trusted_server_ca,
                        server_pin=args.witness_server_leaf_der_sha256,
                        pinned_witness_public_key=args.trusted_witness_public_pem,
                        witness_public_key_pin=args.trusted_witness_public_pem_sha256,
                        tag=args.witness_tag)
            if args.operation == 'serve-once-witness-guarded':
                try:
                    from .audit_record_recovery_witness import (
                        authenticated_head, MAX_SIGNED_BYTES as MAX_WITNESS_SIGNED,
                    )
                except ImportError:
                    from audit_record_recovery_witness import (
                        authenticated_head, MAX_SIGNED_BYTES as MAX_WITNESS_SIGNED,
                    )
                raw_witness = _read_limited(
                    _private_regular_file(args.current_signed_witness_receipt),
                    MAX_WITNESS_SIGNED)
                witness_head = authenticated_head(
                    args.independent_witness_database, raw_witness,
                    args.trusted_witness_public_pem,
                    args.trusted_witness_pem_sha256, tag=args.witness_tag)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((args.host, args.port))
                listener.listen(1)
                listener.settimeout(SOCKET_TIMEOUT)
                accepted = serve_one(
                    listener, args.custodian_database,
                    args.private_ed25519_signing_key,
                    args.tls_server_cert, args.tls_server_key,
                    args.trusted_client_ca,
                    args.expected_client_certificate_der_sha256,
                    tag=args.custodian_tag, witness_head=witness_head,
                    remote_witness_provider=remote_witness_provider,
                    witness_fence_provider=witness_fence_provider)
            result, status = {'request_accepted': accepted,
                              'custodian_witness_guarded': (
                                  witness_head is not None
                                  or remote_witness_provider is not None
                                  or witness_fence_provider is not None),
                              'remote_witness_fenced_during_mutation': (
                                  witness_fence_provider is not None),
                              'remote_witness_fetched_per_mutation': (
                                  remote_witness_provider is not None)}, (
                0 if accepted else 1)
        else:
            offer = (_read_limited(
                _private_regular_file(args.private_checkpoint_offer),
                MAX_CHECKPOINT_BYTES) if args.operation == 'deposit' else None)
            checkpoint, signed, seq = exchange(
                args.host, args.port, hostname=args.tls_hostname,
                cert=args.tls_client_cert, key=args.tls_client_key,
                ca=args.trusted_server_ca,
                server_cert_sha256=args.server_certificate_der_sha256,
                pinned_signing_public_key=args.pinned_ed25519_custodian_public_key,
                signing_public_key_sha256=args.custodian_signing_public_key_sha256,
                tag=args.custodian_tag,
                action=args.operation, checkpoint_raw=offer,
                expected_sequence=(args.expected_sequence
                                   if args.operation == 'deposit' else None),
                expected_receipt_sha256=(args.expected_receipt_sha256
                                         if args.operation == 'deposit' else None))
            _write_new_private(args.private_signed_receipt_output, signed)
            _write_new_private(args.private_checkpoint_output, checkpoint)
            result, status = {
                'private_authenticated_receipt_saved': True,
                'private_authenticated_checkpoint_saved': True,
                'custodian_sequence': seq}, 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError,
            ssl.SSLError, TimeoutError, sqlite3.Error):
        result, status = {
            'valid_input': False,
            'error_code': 'invalid_private_input_or_channel',
        }, 2
    result.update({
        'schema': REPORT_SCHEMA,
        'tls13_mutual_certificates_and_leaf_pins_enforced': status == 0,
        'independent_remote_custodian_deployed': False,
        'trusted_client_and_server_key_provisioning_performed': False,
        'network_level_replay_avoided_by_tls13_and_request_binding': status == 0,
        'external_rollback_prevention_guaranteed': False,
        'cross_database_atomic_commit_guaranteed': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_nonces_or_values_emitted': False,
    })
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
