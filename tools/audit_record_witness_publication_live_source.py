"""Stage 263X: live HTTPS inquiry to a separately enrolled head authority.

A fresh client nonce is sent to an HTTPS endpoint and a size-bounded,
domain-separated Ed25519 response is checked against independently retained
Stage 263W current-head values. No production authority is provisioned here.
The operator MUST keep the pinned authority key and sequence floor outside
the custody host. No fence retirement or writing to custody journals occurs.
"""
import argparse
import hashlib
import hmac
import json
import ipaddress
from pathlib import Path
import re
import secrets
import ssl
import urllib.error
import urllib.parse
import urllib.request

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_replay_head_checkpoint import (
        HEX32, HEX64, TAG, _public_key_identity,
    )
    from .audit_record_witness_publication_latest_head import MAX_COUNT
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_replay_head_checkpoint import (
        HEX32, HEX64, TAG, _public_key_identity,
    )
    from audit_record_witness_publication_latest_head import MAX_COUNT

SCHEMA = 'wild-arms-ps1-live-publication-head-source-v1'
REQUEST_SCHEMA = 'wild-arms-ps1-live-publication-head-request-v1'
REPORT_SCHEMA = 'wild-arms-ps1-live-publication-head-report-v1'
DOMAIN = b'wild-arms-ps1-live-publication-head-source-v1\x00'
MAX_RESPONSE = 2048
MAX_SEQUENCE = 2**63 - 1
FIELDS = {
    'schema', 'source_url', 'authority_id', 'checkpoint_scope',
    'challenge_nonce', 'authority_sequence', 'event_count',
    'head_sha256', 'history_sha256', 'latest_witness_sha256',
    'notary_bundle_sha256', 'witness_fence_retirement_authorized',
}
HOST = re.compile(r'[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]\Z')


class LiveSourceConflict(ValueError):
    """Signed online response conflicts with independently expected state."""


class LiveSourceUnavailable(OSError):
    """TLS, transport or remote service could not complete the inquiry."""


def validate_url(url):
    """Constrain the enrolled HTTPS endpoint, not an attacker-provided redirect."""
    if type(url) is not str or len(url) > 512:
        raise LiveSourceConflict('invalid head authority endpoint')
    try:
        p = urllib.parse.urlsplit(url)
        host = p.hostname
        port = p.port
    except ValueError as exc:
        raise LiveSourceConflict('invalid head authority endpoint') from exc
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise LiveSourceConflict('IP-literal authority URL is disallowed')
    if (p.scheme != 'https' or p.username is not None
            or p.password is not None or p.query or p.fragment
            or not host or not HOST.fullmatch(host)
            or '.' not in host or host.endswith('.')
            or port not in (None, 443) or not p.path.startswith('/')
            or not p.path or not url == urllib.parse.urlunsplit(p)):
        raise LiveSourceConflict('noncanonical or insecure authority URL')
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def fetch_live_receipt(url, scope, challenge, *, timeout=5):
    """One uncached TLS POST; no proxy, redirect, credentials, or retry fallback."""
    validate_url(url)
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise LiveSourceConflict('invalid scope')
    if type(challenge) is not str or not HEX32.fullmatch(challenge):
        raise LiveSourceConflict('invalid challenge')
    raw = _canonical({
        'schema': REQUEST_SCHEMA,
        'checkpoint_scope': scope,
        'challenge_nonce': challenge,
    })
    request = urllib.request.Request(
        url, data=raw, method='POST',
        headers={'Content-Type':'application/json',
                 'Accept':'application/json',
                 'Cache-Control':'no-store'})
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise LiveSourceUnavailable('authority returned non-200 status')
            result = response.read(MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError, ssl.SSLError,
            ConnectionError) as exc:
        raise LiveSourceUnavailable('independent authority unavailable') from exc
    if not 0 < len(result) <= MAX_RESPONSE:
        raise LiveSourceConflict('authority reply is empty or oversized')
    return result


def verify_receipt(raw, *, source_url, scope, challenge, authority_id,
                   authority_public, authority_pin, notary_a_public,
                   notary_a_pin, notary_b_public, notary_b_pin,
                   minimum_sequence, expected_count, expected_head,
                   expected_history, expected_witness, expected_bundle):
    """Authenticate one live response against offline Stage 263W commitments."""
    validate_url(source_url)
    if (type(scope) is not str or not TAG.fullmatch(scope)
            or type(authority_id) is not str or not TAG.fullmatch(authority_id)
            or type(challenge) is not str or not HEX32.fullmatch(challenge)):
        raise LiveSourceConflict('invalid enrolled scope, source or challenge')
    if (type(minimum_sequence) is not int
            or not 0 <= minimum_sequence <= MAX_SEQUENCE
            or type(expected_count) is not int
            or not 0 <= expected_count <= MAX_COUNT):
        raise LiveSourceConflict('invalid independently retained numeric floor')
    for v in (authority_pin, notary_a_pin, notary_b_pin, expected_head,
              expected_history, expected_witness, expected_bundle):
        if type(v) is not str or not HEX64.fullmatch(v):
            raise LiveSourceConflict('invalid independent SHA-256 pin')
    # Independent role keys are checked as actual DER material, not just PEM
    # string formatting; the SHA-256 of each exact enrolled PEM is pinned.
    identities = []
    for key, pin in ((authority_public, authority_pin),
                     (notary_a_public, notary_a_pin),
                     (notary_b_public, notary_b_pin)):
        pem = _read_limited(_private_regular_file(key), 4096)
        if not hmac.compare_digest(hashlib.sha256(pem).hexdigest(), pin):
            raise LiveSourceConflict('untrusted authority/notary PEM pin')
        identities.append(_public_key_identity(key))
    if len(set(identities)) != 3:
        raise LiveSourceConflict('authority and notaries do not have distinct keys')
    body = _signed(raw, SCHEMA, DOMAIN, authority_pin, authority_public)
    if type(body) is not dict or set(body) != FIELDS:
        raise LiveSourceConflict('invalid signed source response shape')
    if (body['schema'] != SCHEMA
            or body['source_url'] != source_url
            or body['authority_id'] != authority_id
            or body['checkpoint_scope'] != scope
            or body['challenge_nonce'] != challenge
            or body['witness_fence_retirement_authorized'] is not False):
        raise LiveSourceConflict('signed source authority, challenge or policy mismatch')
    seq = body['authority_sequence']
    count = body['event_count']
    if (type(seq) is not int or not minimum_sequence <= seq <= MAX_SEQUENCE
            or type(count) is not int or count != expected_count):
        raise LiveSourceConflict('authority sequence rolled back or count diverged')
    for key, expected in (
            ('head_sha256', expected_head),
            ('history_sha256', expected_history),
            ('latest_witness_sha256', expected_witness),
            ('notary_bundle_sha256', expected_bundle)):
        if type(body[key]) is not str or not hmac.compare_digest(body[key], expected):
            raise LiveSourceConflict('authority head differs from independent pin')
    return {
        'schema': REPORT_SCHEMA,
        'verified_online_authority_ed25519_response': True,
        'signed_fresh_client_challenge_matched': True,
        'enrolled_authority_distinct_from_notaries': True,
        'authority_sequence_meets_external_floor': True,
        'exact_stage_263w_latest_tuple_matched': True,
        'authority_sequence': seq,
        'event_count': count,
        'head_sha256': expected_head,
        'independent_head_service_really_deployed_proved': False,
        'remote_global_latest_head_proved': False,
        'external_sequence_floor_independently_stored_proved': False,
        'authority_honestly_reports_latest_proved': False,
        'continuous_availability_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def verify_live(*, fetcher=fetch_live_receipt, challenge=None, **kwargs):
    """Generate a nonce at invocation and fetch before verifying signature."""
    nonce = secrets.token_hex(16) if challenge is None else challenge
    if type(nonce) is not str or not HEX32.fullmatch(nonce):
        raise LiveSourceConflict('invalid fresh nonce')
    raw = fetcher(kwargs['source_url'], kwargs['scope'], nonce)
    return verify_receipt(raw, challenge=nonce, **kwargs)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-url', required=True)
    p.add_argument('--source-public', required=True, type=Path)
    p.add_argument('--source-public-pin', required=True)
    p.add_argument('--authority-id', required=True)
    for role in ('a','b'):
        p.add_argument('--notary-'+role+'-public', required=True, type=Path)
        p.add_argument('--notary-'+role+'-public-pin', required=True)
    p.add_argument('--scope', required=True)
    p.add_argument('--external-minimum-sequence', required=True, type=int)
    p.add_argument('--expected-count', required=True, type=int)
    p.add_argument('--expected-head', required=True)
    p.add_argument('--expected-history-sha256', required=True)
    p.add_argument('--expected-witness-sha256', required=True)
    p.add_argument('--expected-notary-bundle-sha256', required=True)
    a = p.parse_args(argv)
    report = {'schema': REPORT_SCHEMA,
              'witness_fence_retirement_authorized': False,
              'witness_fence_retired': False}
    try:
        report.update(verify_live(
            source_url=a.source_url, scope=a.scope,
            authority_id=a.authority_id,
            authority_public=a.source_public,
            authority_pin=a.source_public_pin,
            notary_a_public=a.notary_a_public,
            notary_a_pin=a.notary_a_public_pin,
            notary_b_public=a.notary_b_public,
            notary_b_pin=a.notary_b_public_pin,
            minimum_sequence=a.external_minimum_sequence,
            expected_count=a.expected_count, expected_head=a.expected_head,
            expected_history=a.expected_history_sha256,
            expected_witness=a.expected_witness_sha256,
            expected_bundle=a.expected_notary_bundle_sha256))
        status = 0
    except LiveSourceUnavailable:
        report['independent_authority_unavailable'] = True
        status = 2
    except (LiveSourceConflict, ValueError, OSError, TypeError,
            KeyError, IndexError):
        report['independent_authority_conflict'] = True
        status = 1
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
