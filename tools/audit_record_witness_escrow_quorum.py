"""Stage 263O: independent three-operator escrow receipt comparison.

Require three independently pinned Ed25519 signatures on the EXACT same
accepted-registry snapshot, a pinned predecessor escrow and an externally
retained digest of all three entire signed envelopes. Re-audit the accepted
registry under one read-only SQLite snapshot.

An archive only becomes independent if operated/stored outside this host.
The verifier cannot prove independent physical storage, receipt freshness,
a complete view of all escrow receipts or protection against replaying an
old registry together with old receipts and old external pins. No unlock.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_replay_head_checkpoint import (
        _public_key_identity, _hex, HEX64, HEX32, TAG,
    )
    from .audit_record_witness_checkpoint_registry import (
        _private_path, _connect, _audit, _check_registry_pin,
        SCHEMA as REGISTRY_SCHEMA, GENESIS as REGISTRY_GENESIS,
        RegistryConflict,
    )
    from .audit_record_witness_replay_head_checkpoint import ANCHOR_GENESIS
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_replay_head_checkpoint import (
        _public_key_identity, _hex, HEX64, HEX32, TAG,
        ANCHOR_GENESIS,
    )
    from audit_record_witness_checkpoint_registry import (
        _private_path, _connect, _audit, _check_registry_pin,
        SCHEMA as REGISTRY_SCHEMA, GENESIS as REGISTRY_GENESIS,
        RegistryConflict,
    )
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA = 'wild-arms-ps1-three-operator-registry-escrow-claim-v1'
REPORT_SCHEMA = 'wild-arms-ps1-three-operator-registry-escrow-audit-v1'
DOMAIN = b'wild-arms-ps1-three-operator-registry-escrow-claim-v1\x00'
PIN_DOMAIN = b'wild-arms-ps1-three-operator-registry-escrow-bundle-v1\x00'
ESCROW_GENESIS = hashlib.sha256(PIN_DOMAIN + b'genesis').hexdigest()
ROLES = ('escrow-a','escrow-b','escrow-c')
MAX_SIGNED = 3072
MAX_EVENTS = 10000
FIELDS = {
    'schema','escrow_role','checkpoint_tag','registry_schema',
    'registry_event_count','registry_head_sha256',
    'latest_checkpoint_sha256','previous_escrow_sha256',
    'escrow_round_nonce','witness_fence_retirement_authorized',
}


class EscrowConflict(ValueError):
    """Missing, inconsistent or stale independent operator receipt."""


def _bound_digest(value, regex=HEX64):
    if type(value) is not str or not regex.fullmatch(value):
        raise EscrowConflict('invalid escrow pin or nonce')
    return value


def make_body(role, count, registry_head, checkpoint, prior, nonce, tag):
    """Unsigned deterministic body: administrators must sign independently."""
    if role not in ROLES:
        raise EscrowConflict('unknown independent escrow signer role')
    if type(count) is not int or not 0 <= count <= MAX_EVENTS:
        raise EscrowConflict('invalid registry event count')
    for value in (registry_head, checkpoint, prior):
        _bound_digest(value)
    _bound_digest(nonce, HEX32)
    if type(tag) is not str or not TAG.fullmatch(tag):
        raise EscrowConflict('invalid escrow scope')
    if count == 0 and (
            registry_head != REGISTRY_GENESIS
            or checkpoint != ANCHOR_GENESIS
            or prior != ESCROW_GENESIS):
        raise EscrowConflict('genesis receipt must use pinned genesis state')
    return {
        'schema': SCHEMA,
        'escrow_role': role,
        'checkpoint_tag': tag,
        'registry_schema': REGISTRY_SCHEMA,
        'registry_event_count': count,
        'registry_head_sha256': registry_head,
        'latest_checkpoint_sha256': checkpoint,
        'previous_escrow_sha256': prior,
        'escrow_round_nonce': nonce,
        'witness_fence_retirement_authorized': False,
    }


def bundle_digest(signed_receipts):
    """Candidate digest; only out-of-band escrow can make it trustworthy."""
    if type(signed_receipts) is not dict or set(signed_receipts) != set(ROLES):
        raise EscrowConflict('three ordered distinct escrow receipts required')
    for role in ROLES:
        raw = signed_receipts[role]
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_SIGNED:
            raise EscrowConflict('invalid bounded signed escrow receipt')
    bindings = {
        'schema': SCHEMA,
        'signed_receipts': {
            role: hashlib.sha256(signed_receipts[role]).hexdigest()
            for role in ROLES
        },
    }
    return hashlib.sha256(PIN_DOMAIN + _canonical(bindings)).hexdigest()


def verify(registry_path, signed_receipts, public_paths, public_pins, *,
           checkpoint_tag, prior_escrow_pin, independently_pinned_bundle,
           expected_registry_count, expected_registry_head,
           expected_latest_checkpoint):
    """All 3 signatures, same round, pinned bundle and one SQLite snapshot."""
    if (type(signed_receipts) is not dict or set(signed_receipts) != set(ROLES)
            or type(public_paths) is not dict or set(public_paths) != set(ROLES)
            or type(public_pins) is not dict or set(public_pins) != set(ROLES)):
        raise EscrowConflict('all three independent escrow roles required')
    for value in (prior_escrow_pin, independently_pinned_bundle,
                  expected_registry_head, expected_latest_checkpoint):
        _bound_digest(value)
    if type(expected_registry_count) is not int:
        raise EscrowConflict('invalid independently retained event count')
    if type(checkpoint_tag) is not str or not TAG.fullmatch(checkpoint_tag):
        raise EscrowConflict('invalid externally enrolled scope')

    bodies = {}
    key_material = set()
    pins = set()
    for role in ROLES:
        pin = _bound_digest(public_pins[role])
        if pin in pins:
            raise EscrowConflict('duplicated escrow public key enrollment')
        pins.add(pin)
        body = _signed(signed_receipts[role], SCHEMA, DOMAIN, pin,
                       public_paths[role])
        identity = _public_key_identity(public_paths[role])
        if identity in key_material:
            raise EscrowConflict('same public key under different PEM encoding')
        key_material.add(identity)
        if type(body) is not dict or set(body) != FIELDS:
            raise EscrowConflict('unexpected signed escrow fields')
        if body != make_body(
                role, body['registry_event_count'], body['registry_head_sha256'],
                body['latest_checkpoint_sha256'],
                body['previous_escrow_sha256'],
                body['escrow_round_nonce'], body['checkpoint_tag']):
            raise EscrowConflict('unsafe or malformed signed operator statement')
        bodies[role] = body

    first = bodies[ROLES[0]]
    for role in ROLES[1:]:
        other = bodies[role]
        if {k:v for k,v in other.items() if k != 'escrow_role'} != {
                k:v for k,v in first.items() if k != 'escrow_role'}:
            raise EscrowConflict('conflicting independently signed registry heads')
    if (first['checkpoint_tag'] != checkpoint_tag
            or first['previous_escrow_sha256'] != prior_escrow_pin
            or first['registry_event_count'] != expected_registry_count
            or not hmac.compare_digest(
                first['registry_head_sha256'], expected_registry_head)
            or not hmac.compare_digest(
                first['latest_checkpoint_sha256'],
                expected_latest_checkpoint)):
        raise EscrowConflict('escrow round differs from independently pinned tip')
    actual = bundle_digest(signed_receipts)
    if not hmac.compare_digest(actual, independently_pinned_bundle):
        raise EscrowConflict('three signed receipts differ from external bundle pin')

    path = _private_path(registry_path, exists=True)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count, head, checkpoint, _, scope, _ = _audit(con)
            try:
                _check_registry_pin(
                    count, head, expected_registry_count,
                    expected_registry_head)
            except RegistryConflict as exc:
                raise EscrowConflict('registry differs from external head') from exc
            if (not hmac.compare_digest(checkpoint,
                                        expected_latest_checkpoint)
                    or (scope is not None and scope != checkpoint_tag)):
                raise EscrowConflict('registry checkpoint or scope changed')
        finally:
            con.rollback()
    return {
        'schema': REPORT_SCHEMA,
        'three_distinct_operator_signatures_verified': True,
        'signed_registry_head_matches_current_snapshot': True,
        'all_supplied_operator_receipts_agree': True,
        'independently_pinned_receipt_bundle_matches': True,
        'previous_escrow_checkpoint_matches_pin': True,
        'registry_event_count': count,
        'registry_head_sha256': head,
        'latest_checkpoint_sha256': checkpoint,
        'escrow_bundle_sha256': actual,
        'independent_physical_archive_storage_proved': False,
        'all_possible_conflicting_receipts_discovered': False,
        'continuous_escrow_freshness_proved': False,
        'historical_replay_with_old_pins_excluded': False,
        'global_writer_revocation_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_registry', type=Path)
    parser.add_argument('--checkpoint-tag', required=True)
    parser.add_argument('--prior-escrow-sha256', required=True)
    parser.add_argument('--latest-escrow-sha256', required=True)
    parser.add_argument('--expected-count', type=int, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-checkpoint', required=True)
    for role in ROLES:
        parser.add_argument('--'+role+'-signed', type=Path, required=True)
        parser.add_argument('--'+role+'-public', type=Path, required=True)
        parser.add_argument('--'+role+'-public-sha256', required=True)
    args = parser.parse_args(argv)
    response = {
        'schema': REPORT_SCHEMA,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
    }
    try:
        raw = {
            role: _read_limited(
                _private_regular_file(getattr(args, role.replace('-','_')+
                                       '_signed')), MAX_SIGNED)
            for role in ROLES
        }
        pubs = {
            role: getattr(args, role.replace('-','_')+'_public')
            for role in ROLES
        }
        pins = {
            role: getattr(args, role.replace('-','_')+'_public_sha256')
            for role in ROLES
        }
        response.update(verify(
            args.private_registry, raw, pubs, pins,
            checkpoint_tag=args.checkpoint_tag,
            prior_escrow_pin=args.prior_escrow_sha256,
            independently_pinned_bundle=args.latest_escrow_sha256,
            expected_registry_count=args.expected_count,
            expected_registry_head=args.expected_head,
            expected_latest_checkpoint=args.expected_checkpoint))
        code = 0
    except (EscrowConflict, RegistryConflict):
        response['conflicting_or_untrusted_escrow'] = True
        code = 1
    except (ValueError, OSError, TypeError, KeyError, IndexError):
        response['valid_input'] = False
        code = 2
    print(json.dumps(response, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
