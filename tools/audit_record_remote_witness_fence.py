"""Mutually authenticated, Ed25519-signed remote witness claim and release.

Clients first fetch a fresh signed event prefix (stage 260) and submit
an exact-head CAS claim. The witness prevents new recovery events from
being appended until an exact-token release. Both operations have fresh
128-bit network challenges and are signed with a separate domain.

A crashed custodian may strand the witness fence, deliberately fail closed.
This protocol does NOT provide a distributed SQL transaction.
"""
from contextlib import contextmanager
import hashlib
import hmac
from pathlib import Path
import secrets
import socket
import sqlite3

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _digest, _parse, _read_limited
    from .audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_remote_recovery_witness import (
        _body, _check_signed_reply, fetch_head,
    )
    from .audit_record_custodian_tls import (
        _tls_context, _peer_pin, _receive, _send, SOCKET_TIMEOUT,
    )
    from .audit_record_witness_fence import claim, release, _owner
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _digest, _parse, _read_limited
    from audit_record_signed_custodian import _openssl, _tag, MAX_PEM_BYTES
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_remote_recovery_witness import (
        _body, _check_signed_reply, fetch_head,
    )
    from audit_record_custodian_tls import (
        _tls_context, _peer_pin, _receive, _send, SOCKET_TIMEOUT,
    )
    from audit_record_witness_fence import claim, release, _owner

REQUEST_SCHEMA = 'wild-arms-ps1-remote-witness-fence-request-v1'
RESPONSE_SCHEMA = 'wild-arms-ps1-remote-witness-fence-response-v1'
DOMAIN = b'wild-arms-ps1-remote-witness-fence-response-v1\x00'
HEX = set('0123456789abcdef')
BASE_REPLY = {
    'schema', 'action', 'request_id', 'fence_owner_sha256',
    'custody_request_sha256', 'witness_tag', 'recovery_count',
    'last_recovery_event_sha256', 'witness_chain_sha256', 'recovery_events',
}
MAX_REPLY = 1024*1024


def _hex(value, length):
    return type(value) is str and len(value) == length and all(
        character in HEX for character in value)


def _validate(request):
    if (type(request) is not dict or
            request.get('schema') != REQUEST_SCHEMA or
            request.get('action') not in ('claim-head', 'release-head') or
            not _hex(request.get('request_id'), 32) or
            not _hex(request.get('fence_token'), 32) or
            not _hex(request.get('custody_request_sha256'), 64)):
        raise ValueError('invalid private remote witness fence request')
    wanted = {
        'schema', 'action', 'request_id', 'fence_token',
        'custody_request_sha256',
    }
    if request['action'] == 'claim-head':
        wanted.update({'expected_count', 'expected_chain_sha256'})
        if (type(request.get('expected_count')) is not int
                or request['expected_count'] < 0
                or not _hex(request.get('expected_chain_sha256'), 64)):
            raise ValueError('invalid conditional independent witness head')
    if set(request) != wanted:
        raise ValueError('unexpected remote witness fence fields')
    return request


def handle(request, witness_db, signing_key, tag):
    """Server-side operation after exact mutual TLS client authentication."""
    request = _validate(request)
    signing = _private_regular_file(signing_key)
    if signing.stat().st_size > MAX_PEM_BYTES:
        raise ValueError('invalid private witness signer')
    action = request['action']
    if action == 'claim-head':
        claim(
            witness_db, request['fence_token'],
            request['custody_request_sha256'],
            request['expected_count'],
            request['expected_chain_sha256'])
    else:
        release(witness_db, request['fence_token'],
                request['custody_request_sha256'])
    head = _body(witness_db, request['request_id'], tag)
    body = {
        'schema': RESPONSE_SCHEMA, 'action': action,
        'request_id': request['request_id'],
        'fence_owner_sha256': _owner(request['fence_token']),
        'custody_request_sha256': request['custody_request_sha256'],
        **{k: head[k] for k in (
            'witness_tag', 'recovery_count',
            'last_recovery_event_sha256', 'witness_chain_sha256',
            'recovery_events')},
    }
    signed = _openssl(signing, DOMAIN + _canonical(body))
    return {**body, 'signature_hex': signed.hex()}


def _verify(response, request, tag, public_key, pem_pin):
    _digest(pem_pin)
    _validate(request)
    if (type(response) is not dict or
            set(response) != BASE_REPLY | {'signature_hex'} or
            response.get('schema') != RESPONSE_SCHEMA or
            response['action'] != request['action'] or
            response['request_id'] != request['request_id'] or
            response['fence_owner_sha256'] != _owner(request['fence_token']) or
            response['custody_request_sha256'] != request['custody_request_sha256'] or
            response['witness_tag'] != _tag(tag) or
            not _hex(response.get('signature_hex'), 128)):
        raise ValueError('wrong or replayed signed witness fence response')
    body = {k: response[k] for k in BASE_REPLY}
    key = _private_regular_file(public_key)
    pem = _read_limited(key, MAX_PEM_BYTES)
    if not hmac.compare_digest(hashlib.sha256(pem).hexdigest(), pem_pin):
        raise ValueError('remote witness pin mismatch')
    if not _openssl(
            key, DOMAIN + _canonical(body),
            signature=bytes.fromhex(response['signature_hex']),
            public_key_bytes=pem):
        raise ValueError('invalid independently signed witness fence')
    # Reuse the stage-260 exact event and witness-chain validation, with
    # the stage-261 signatures already verified separately above.
    from .audit_record_recovery_witness import _validate_events, WITNESS_DOMAIN
    from .audit_record_anchor_handoff import GENESIS
    events = response['recovery_events']
    _validate_events(events, require_nonempty=False)
    chain = GENESIS
    for event in events:
        raw = _canonical(event)
        if len(raw) > 2048:
            raise ValueError('oversized witness recovery event')
        chain = hashlib.sha256(
            WITNESS_DOMAIN + bytes.fromhex(chain) + raw).hexdigest()
    if (type(response['recovery_count']) is not int
            or response['recovery_count'] != len(events)
            or response['last_recovery_event_sha256'] !=
                (events[-1]['event_sha256'] if events else GENESIS)
            or response['witness_chain_sha256'] != chain):
        raise ValueError('inconsistent independent witness fence history')
    return (
        len(events), response['last_recovery_event_sha256'], chain,
        [_canonical(e) for e in events])


def exchange_fence(host, port, *, hostname, cert, key, ca, server_pin,
                   public_key, public_pin, tag, action, token,
                   custody_request_sha256, expected=None):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid witness fence network port')
    _digest(server_pin)
    context = _tls_context(cert, key, ca, server=False)
    request = {
        'schema': REQUEST_SCHEMA, 'action': action,
        'request_id': secrets.token_hex(16),
        'fence_token': token,
        'custody_request_sha256': custody_request_sha256,
    }
    if action == 'claim-head':
        if (type(expected) not in (tuple, list)
                or len(expected) != 4):
            raise ValueError('exact fresh witness head is required')
        request['expected_count'] = expected[0]
        request['expected_chain_sha256'] = expected[2]
    _validate(request)
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT) as sock:
        sock.settimeout(SOCKET_TIMEOUT)
        with context.wrap_socket(sock, server_hostname=hostname) as tls:
            _peer_pin(tls, server_pin)
            _send(tls, request)
            response = _receive(tls)
    head = _verify(response, request, tag, public_key, public_pin)
    if action == 'claim-head' and head != tuple(expected):
        raise ValueError('signed witness claim does not match requested head')
    return head


@contextmanager
def fenced_custody_request(custody_request, *, witness_host, witness_port,
                           hostname, cert, key, ca, server_pin,
                           public_key, public_pin, tag):
    """Acquire remote CAS, hold fence until local custody write completes."""
    if (type(custody_request) is not dict or
            custody_request.get('action') not in (
                'reserve', 'deposit', 'deposit-reserved')):
        raise ValueError('unexpected custody request for witness fence')
    token = custody_request.get('request_id')
    if not _hex(token, 32):
        raise ValueError('custody request missing stable fence identity')
    digest = hashlib.sha256(
        b'wild-arms-ps1-custody-request-fence-v1\x00'
        + _canonical(custody_request)).hexdigest()
    common = {
        'hostname': hostname, 'cert': cert, 'key': key, 'ca': ca,
        'server_pin': server_pin, 'public_key': public_key,
        'public_pin': public_pin, 'tag': tag,
        'token': token, 'custody_request_sha256': digest,
    }
    latest = fetch_head(
        witness_host, witness_port, hostname=hostname,
        cert=cert, key=key, ca=ca, server_pin=server_pin,
        pinned_witness_public_key=public_key,
        witness_public_key_pin=public_pin, tag=tag)
    claimed = exchange_fence(
        witness_host, witness_port, **common,
        action='claim-head', expected=latest)
    try:
        yield claimed
    finally:
        # Release only AFTER local custody SQLite commit/rollback. If
        # this fails, the remote witness intentionally retains the
        # durable owner fence until the exact token is reconciled.
        exchange_fence(
            witness_host, witness_port, **common, action='release-head')
