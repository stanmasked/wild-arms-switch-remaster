"""Stage 263S: two independently signed publication-mirror snapshot claims.

Read-only verification binds two separately pinned Ed25519 administrator
signatures to the SAME complete Stage 263R mirror snapshot and to an
independently retained SHA-256 of BOTH complete signed envelopes.
An external predecessor digest and observation epoch make every claim
explicitly scoped; neither proves a trusted monotonic latest head.

This is not remote storage attestation, global anti-rollback, or permission
to release an indeterminate witness fence.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_replay_head_checkpoint import (
        _public_key_identity, HEX64, HEX32, TAG,
    )
    from .audit_record_witness_publication_intake import GENESIS as INTAKE_GENESIS
    from .audit_record_witness_publication_mirror import (
        compare as compare_mirrors, MirrorConflict,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_replay_head_checkpoint import (
        _public_key_identity, HEX64, HEX32, TAG,
    )
    from audit_record_witness_publication_intake import GENESIS as INTAKE_GENESIS
    from audit_record_witness_publication_mirror import (
        compare as compare_mirrors, MirrorConflict,
    )

SCHEMA = 'wild-arms-ps1-dual-signed-publication-mirror-witness-v1'
REPORT_SCHEMA = 'wild-arms-ps1-dual-signed-publication-mirror-audit-v1'
DOMAIN = b'wild-arms-ps1-dual-signed-publication-mirror-witness-v1\x00'
BUNDLE_DOMAIN = b'wild-arms-ps1-dual-signed-publication-mirror-bundle-v1\x00'
WITNESS_GENESIS = hashlib.sha256(BUNDLE_DOMAIN + b'genesis').hexdigest()
ROLES = ('mirror-admin-a', 'mirror-admin-b')
MAX_SIGNED = 3072
MAX_EPOCH = 1000000
MAX_COUNT = 96
FIELDS = {
    'schema','admin_role','mirror_scope','observation_epoch',
    'mirror_event_count','mirror_head_sha256','intake_frozen_by_conflict',
    'prior_witness_sha256','witness_nonce',
    'witness_fence_retirement_authorized',
}


class MirrorWitnessConflict(ValueError):
    """Missing, stale, tampered or contradictory signed mirror observation."""


def _hash(value, regex=HEX64):
    if type(value) is not str or not regex.fullmatch(value):
        raise MirrorWitnessConflict('invalid enrolled digest or witness nonce')
    return value


def make_body(role, epoch, count, head, frozen, prior, nonce, scope):
    """Generate deterministic UNSIGNED claim; independent admins sign offline."""
    if role not in ROLES:
        raise MirrorWitnessConflict('invalid mirror witness administrator role')
    if type(epoch) is not int or not 0 <= epoch <= MAX_EPOCH:
        raise MirrorWitnessConflict('invalid mirror witness observation epoch')
    if type(count) is not int or not 0 <= count <= MAX_COUNT:
        raise MirrorWitnessConflict('invalid mirror witness count')
    if type(frozen) is not bool:
        raise MirrorWitnessConflict('invalid mirror witness conflict state')
    _hash(head)
    _hash(prior)
    _hash(nonce, HEX32)
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise MirrorWitnessConflict('invalid mirror witness scope')
    if epoch == 0 and (count != 0 or head != INTAKE_GENESIS
                       or frozen or prior != WITNESS_GENESIS):
        raise MirrorWitnessConflict('initial witness must bind genesis history')
    return {
        'schema': SCHEMA,
        'admin_role': role,
        'mirror_scope': scope,
        'observation_epoch': epoch,
        'mirror_event_count': count,
        'mirror_head_sha256': head,
        'intake_frozen_by_conflict': frozen,
        'prior_witness_sha256': prior,
        'witness_nonce': nonce,
        'witness_fence_retirement_authorized': False,
    }


def witness_digest(signed_a, signed_b):
    """Local candidate only; trust requires separate off-host enrollment."""
    if (type(signed_a) is not bytes or type(signed_b) is not bytes
            or not 0 < len(signed_a) <= MAX_SIGNED
            or not 0 < len(signed_b) <= MAX_SIGNED):
        raise MirrorWitnessConflict('invalid signed witness envelope size')
    item = {
        'schema': SCHEMA,
        'admin_a_signed_sha256': hashlib.sha256(signed_a).hexdigest(),
        'admin_b_signed_sha256': hashlib.sha256(signed_b).hexdigest(),
    }
    return hashlib.sha256(BUNDLE_DOMAIN + _canonical(item)).hexdigest()


def verify(a_path, a_count, a_head, b_path, b_count, b_head,
           signed_a, public_a, public_a_pin,
           signed_b, public_b, public_b_pin, *,
           scope, prior_witness_pin, latest_witness_pin):
    """Check exact role signatures, independent whole-bundle pin and mirrors."""
    _hash(prior_witness_pin)
    _hash(latest_witness_pin)
    _hash(public_a_pin)
    _hash(public_b_pin)
    if hmac.compare_digest(public_a_pin, public_b_pin):
        raise MirrorWitnessConflict('duplicate administrator PEM pin')
    if hmac.compare_digest(
            _public_key_identity(public_a), _public_key_identity(public_b)):
        raise MirrorWitnessConflict('duplicate administrator public key material')

    a = _signed(signed_a, SCHEMA, DOMAIN, public_a_pin, public_a)
    b = _signed(signed_b, SCHEMA, DOMAIN, public_b_pin, public_b)
    for role, body in ((ROLES[0], a), (ROLES[1], b)):
        if type(body) is not dict or set(body) != FIELDS:
            raise MirrorWitnessConflict('unexpected mirror witness claim fields')
        if body != make_body(
                role, body['observation_epoch'], body['mirror_event_count'],
                body['mirror_head_sha256'], body['intake_frozen_by_conflict'],
                body['prior_witness_sha256'], body['witness_nonce'],
                body['mirror_scope']):
            raise MirrorWitnessConflict('unsafe or invalid signed mirror witness')
    if {k:v for k,v in a.items() if k != 'admin_role'} != {
            k:v for k,v in b.items() if k != 'admin_role'}:
        raise MirrorWitnessConflict('two administrators signed different snapshots')
    if (a['mirror_scope'] != scope or
            a['prior_witness_sha256'] != prior_witness_pin):
        raise MirrorWitnessConflict('signed scope or predecessor pin mismatch')

    actual = witness_digest(signed_a, signed_b)
    if not hmac.compare_digest(actual, latest_witness_pin):
        raise MirrorWitnessConflict('whole signed witness differs from external pin')

    observed = compare_mirrors(a_path, a_count, a_head,
                               b_path, b_count, b_head)
    if (observed['event_count'] != a['mirror_event_count']
            or not hmac.compare_digest(a_head, a['mirror_head_sha256'])
            or not hmac.compare_digest(b_head, a['mirror_head_sha256'])
            or observed['intake_frozen_by_conflict'] !=
            a['intake_frozen_by_conflict']):
        raise MirrorWitnessConflict('live mirror state differs from signed observation')

    return {
        'schema': REPORT_SCHEMA,
        'two_distinct_ed25519_mirror_signatures_verified': True,
        'both_mirror_chains_and_signed_heads_match': True,
        'signed_conflict_freeze_state_matches': True,
        'separately_pinned_whole_witness_digest_matches': True,
        'signed_predecessor_digest_matches_external_pin': True,
        'observation_epoch': a['observation_epoch'],
        'mirror_event_count': a['mirror_event_count'],
        'witness_sha256': actual,
        'independent_physical_witness_storage_proved': False,
        'observation_epoch_is_globally_monotonic_proved': False,
        'continuous_freshness_or_rollback_exclusion_proved': False,
        'hidden_conflicting_witnesses_excluded': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mirror_a_path', type=Path)
    p.add_argument('mirror_b_path', type=Path)
    for role in ('a','b'):
        p.add_argument('--'+role+'-count', type=int, required=True)
        p.add_argument('--'+role+'-head', required=True)
        p.add_argument('--admin-'+role+'-signed', type=Path, required=True)
        p.add_argument('--admin-'+role+'-public', type=Path, required=True)
        p.add_argument('--admin-'+role+'-public-pin', required=True)
    p.add_argument('--scope', required=True)
    p.add_argument('--prior-witness-sha256', required=True)
    p.add_argument('--latest-witness-sha256', required=True)
    args = p.parse_args(argv)
    result = {
        'schema': REPORT_SCHEMA,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
    }
    try:
        def read(path):
            return _read_limited(_private_regular_file(path), MAX_SIGNED)
        result.update(verify(
            args.mirror_a_path,args.a_count,args.a_head,
            args.mirror_b_path,args.b_count,args.b_head,
            read(args.admin_a_signed),args.admin_a_public,
            args.admin_a_public_pin,
            read(args.admin_b_signed),args.admin_b_public,
            args.admin_b_public_pin,
            scope=args.scope,
            prior_witness_pin=args.prior_witness_sha256,
            latest_witness_pin=args.latest_witness_sha256))
        status=0
    except (MirrorWitnessConflict,MirrorConflict,ValueError):
        result['signed_mirror_witness_conflict']=True
        status=1
    except (OSError,TypeError,KeyError):
        result['valid_input']=False
        status=2
    print(json.dumps(result,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
