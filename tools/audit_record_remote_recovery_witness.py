"""One-shot mutual-TLS remote recovery witness with signed nonce-bound event prefix.

Only the separately administered witness server reads its private witness
SQLite database. The custodian retrieves a fresh complete high-water prefix,
verifies an Ed25519 signature over the client challenge AND the full event
list, and compares it against custody under its existing SQLite write lock.

Reference protocol, not a deployed independent witness or distributed CAS.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl

try:
    from .audit_record_recovery_witness import (
        _head, _validate_events, _receipt, WITNESS_DOMAIN, MAX_EVENTS,
    )
    from .audit_record_custodian_tls import (
        _tls_context, _peer_pin, _receive, _send, SOCKET_TIMEOUT,
    )
    from .audit_record_anchor_handoff import _canonical, GENESIS
    from .audit_record_capture_stream_binding import _digest, _parse, _read_limited
    from .audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    from audit_record_recovery_witness import (
        _head, _validate_events, _receipt, WITNESS_DOMAIN, MAX_EVENTS,
    )
    from audit_record_custodian_tls import (
        _tls_context, _peer_pin, _receive, _send, SOCKET_TIMEOUT,
    )
    from audit_record_anchor_handoff import _canonical, GENESIS
    from audit_record_capture_stream_binding import _digest, _parse, _read_limited
    from audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from audit_record_verifier_checkpoint import _private_regular_file

REQUEST_SCHEMA = 'wild-arms-ps1-remote-recovery-witness-request-v1'
RESPONSE_SCHEMA = 'wild-arms-ps1-remote-recovery-witness-response-v1'
REPORT_SCHEMA = 'wild-arms-ps1-remote-recovery-witness-audit-v1'
SIGN_DOMAIN = b'wild-arms-ps1-remote-recovery-witness-response-v1\x00'
BODY_FIELDS = {
    'schema', 'request_id', 'witness_tag', 'recovery_count',
    'last_recovery_event_sha256', 'witness_chain_sha256', 'recovery_events',
}
MAX_EVENT_JSON_BYTES = 2048


def _request(request):
    if (type(request) is not dict or set(request) != {
            'schema', 'action', 'request_id'}
            or request['schema'] != REQUEST_SCHEMA
            or request['action'] != 'fresh-head'
            or type(request['request_id']) is not str
            or len(request['request_id']) != 32
            or any(ch not in '0123456789abcdef'
                   for ch in request['request_id'])):
        raise ValueError('invalid remote witness challenge')
    return request['request_id']


def _body(witness_db, request_id, tag):
    head = _head(witness_db)
    events = [_parse(raw) for raw in head[3]]
    _validate_events(events, require_nonempty=False)
    return {
        'schema': RESPONSE_SCHEMA,
        'request_id': request_id,
        'witness_tag': _tag(tag),
        'recovery_count': head[0],
        'last_recovery_event_sha256': head[1],
        'witness_chain_sha256': head[2],
        'recovery_events': events,
    }


def _reply(request, witness_db, signing_key, tag):
    request_id = _request(request)
    signer = _private_regular_file(signing_key)
    if signer.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('oversized witness signing key')
    body = _body(witness_db, request_id, tag)
    signature = _openssl(signer, SIGN_DOMAIN + _canonical(body))
    return {**body, 'signature_hex': signature.hex()}


def serve_one(listener, witness_db, signing_key, cert, key, ca,
              expected_client_pin, *, tag):
    """Handle one pinned, mutually authenticated TLS 1.3 witness request."""
    ctx = _tls_context(cert, key, ca, server=True)
    _digest(expected_client_pin)
    with listener.accept()[0] as conn:
        conn.settimeout(SOCKET_TIMEOUT)
        try:
            with ctx.wrap_socket(conn, server_side=True) as tls:
                _peer_pin(tls, expected_client_pin)
                request = _receive(tls)
                try:
                    answer = _reply(request, witness_db, signing_key, tag)
                except (OSError, ValueError, sqlite3.Error):
                    _send(tls, {
                        'schema': RESPONSE_SCHEMA, 'status': 'rejected',
                        'request_id': request.get('request_id', '')
                        if type(request) is dict else '',
                    })
                    return False
                _send(tls, answer)
                return True
        except (OSError, ValueError, ssl.SSLError, sqlite3.Error):
            return False


def _check_signed_reply(reply, nonce, expected_tag, public_key, public_pin):
    _digest(public_pin)
    if (type(reply) is not dict or set(reply) != BODY_FIELDS | {'signature_hex'}
            or reply.get('schema') != RESPONSE_SCHEMA
            or reply.get('request_id') != nonce
            or reply.get('witness_tag') != _tag(expected_tag)
            or type(reply.get('signature_hex')) is not str
            or len(reply['signature_hex']) != 128
            or any(c not in '0123456789abcdef'
                   for c in reply['signature_hex'])):
        raise ValueError('invalid or replayed remote witness reply')
    body = {key: reply[key] for key in BODY_FIELDS}
    key = _private_regular_file(public_key)
    public_pem = _read_limited(key, MAX_PEM_BYTES)
    if not hmac.compare_digest(
            hashlib.sha256(public_pem).hexdigest(), public_pin):
        raise ValueError('untrusted remote witness public key')
    if not _openssl(key, SIGN_DOMAIN + _canonical(body),
                    signature=bytes.fromhex(reply['signature_hex']),
                    public_key_bytes=public_pem):
        raise ValueError('remote witness Ed25519 signature mismatch')
    events = reply['recovery_events']
    _validate_events(events, require_nonempty=False)
    count = reply['recovery_count']
    if type(count) is not int or count != len(events):
        raise ValueError('remote witness count does not match events')
    last_event = GENESIS
    chain = GENESIS
    raw_events = []
    for event in events:
        raw = _canonical(event)
        if len(raw) > MAX_EVENT_JSON_BYTES:
            raise ValueError('oversized remote witness event')
        last_event = event['event_sha256']
        chain = hashlib.sha256(
            WITNESS_DOMAIN + bytes.fromhex(chain) + raw).hexdigest()
        raw_events.append(raw)
    for field, expected in (
            ('last_recovery_event_sha256', last_event),
            ('witness_chain_sha256', chain)):
        _digest(reply[field])
        if reply[field] != expected:
            raise ValueError('inconsistent signed remote witness chain')
    return count, last_event, chain, raw_events


def fetch_head(host, port, *, hostname, cert, key, ca, server_pin,
               pinned_witness_public_key, witness_public_key_pin, tag):
    """Retrieve fresh witness state without opening the witness SQLite DB."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid remote witness port')
    if type(hostname) is not str or not hostname:
        raise ValueError('invalid remote witness TLS hostname')
    _digest(server_pin)
    _tag(tag)
    context = _tls_context(cert, key, ca, server=False)
    challenge = secrets.token_hex(16)
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT) as conn:
        conn.settimeout(SOCKET_TIMEOUT)
        with context.wrap_socket(conn, server_hostname=hostname) as tls:
            _peer_pin(tls, server_pin)
            _send(tls, {
                'schema': REQUEST_SCHEMA, 'action': 'fresh-head',
                'request_id': challenge})
            response = _receive(tls)
    return _check_signed_reply(
        response, challenge, tag,
        pinned_witness_public_key, witness_public_key_pin)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest='mode', required=True)
    server = command.add_parser('serve-once')
    server.add_argument('witness_database', type=Path)
    server.add_argument('private_ed25519_signing_key', type=Path)
    server.add_argument('tls_server_cert', type=Path)
    server.add_argument('tls_server_key', type=Path)
    server.add_argument('trusted_client_ca', type=Path)
    server.add_argument('expected_client_leaf_der_sha256')
    server.add_argument('--witness-tag', required=True)
    server.add_argument('--host', default='127.0.0.1')
    server.add_argument('--port', type=int, required=True)
    client = command.add_parser('fetch-head')
    client.add_argument('host')
    client.add_argument('port', type=int)
    client.add_argument('tls_hostname')
    client.add_argument('tls_client_cert', type=Path)
    client.add_argument('tls_client_key', type=Path)
    client.add_argument('trusted_server_ca', type=Path)
    client.add_argument('pinned_server_leaf_der_sha256')
    client.add_argument('trusted_witness_public_pem', type=Path)
    client.add_argument('trusted_witness_public_pem_sha256')
    client.add_argument('--witness-tag', required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'serve-once':
            if not 1 <= args.port <= 65535:
                raise ValueError('invalid witness listener port')
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((args.host, args.port))
                listener.listen(1)
                listener.settimeout(SOCKET_TIMEOUT)
                ok = serve_one(
                    listener, args.witness_database,
                    args.private_ed25519_signing_key, args.tls_server_cert,
                    args.tls_server_key, args.trusted_client_ca,
                    args.expected_client_leaf_der_sha256,
                    tag=args.witness_tag)
            status, result = (0 if ok else 1), {
                'authenticated_witness_request_served': ok,
            }
        else:
            head = fetch_head(
                args.host, args.port, hostname=args.tls_hostname,
                cert=args.tls_client_cert, key=args.tls_client_key,
                ca=args.trusted_server_ca,
                server_pin=args.pinned_server_leaf_der_sha256,
                pinned_witness_public_key=args.trusted_witness_public_pem,
                witness_public_key_pin=args.trusted_witness_public_pem_sha256,
                tag=args.witness_tag)
            status, result = 0, {
                'fresh_remote_witness_head_authenticated': True,
                'recovery_event_count': head[0],
            }
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            OverflowError, sqlite3.Error, ssl.SSLError):
        status, result = 2, {
            'valid_input': False,
            'error_code': 'invalid_private_witness_or_network',
        }
    result.update({
        'schema': REPORT_SCHEMA,
        'remote_witness_sqlite_opened_by_client': False,
        'independent_production_witness_deployed': False,
        'cross_database_atomicity_guaranteed': False,
        'native_switch_game_build_verified': False,
        'original_ps1_execution_verified': False,
        'private_witness_chain_or_key_emitted': False,
    })
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
