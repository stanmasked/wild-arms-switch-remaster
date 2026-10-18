"""Stage 263W: independently challenged latest signed publication-head claim.

Two independent Ed25519 notaries sign the SAME externally challenged
old-to-new Stage 263V transition. Require a separately retained exact
full-envelope bundle SHA-256, a nonce supplied by the verifier and an
externally retained CURRENT latest (count, head, archive, witness) tuple.

This fails closed when an old certificate is replayed against a NEW,
trusted outside-the-host pin/challenge. It CANNOT assert that supplied
pins or the challenge are actually fresh, or independently persisted.
There is no network lookup, monotonic hardware counter or unlock path.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_replay_head_checkpoint import (
        HEX64, HEX32, TAG, _public_key_identity,
    )
    from .audit_record_witness_publication_transition import (
        verify as verify_transition, TransitionConflict,
    )
    from .audit_record_witness_publication_mirror_history import MAX_ARCHIVE
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_replay_head_checkpoint import (
        HEX64, HEX32, TAG, _public_key_identity,
    )
    from audit_record_witness_publication_transition import (
        verify as verify_transition, TransitionConflict,
    )
    from audit_record_witness_publication_mirror_history import MAX_ARCHIVE

SCHEMA = 'wild-arms-ps1-challenged-latest-publication-head-v1'
REPORT_SCHEMA = 'wild-arms-ps1-challenged-latest-publication-report-v1'
DOMAIN = b'wild-arms-ps1-challenged-latest-publication-head-v1\x00'
BUNDLE_DOMAIN = b'wild-arms-ps1-challenged-latest-publication-bundle-v1\x00'
ROLES = ('notary-a','notary-b')
MAX_SIGNED = 4096
MAX_COUNT = 96
FIELDS = {
    'schema','notary_role','checkpoint_scope','challenge_nonce',
    'old_event_count','old_head_sha256','old_history_sha256',
    'old_latest_witness_sha256',
    'new_event_count','new_head_sha256','new_history_sha256',
    'new_latest_witness_sha256','witness_fence_retirement_authorized',
}


class LatestHeadConflict(ValueError):
    """An untrusted, stale or conflicting latest-head notary endorsement."""


def _digest(raw, regex=HEX64):
    if type(raw) is not str or not regex.fullmatch(raw):
        raise LatestHeadConflict('invalid external digest or challenge')
    return raw


def make_body(role,scope,challenge,old_count,old_head,old_history,old_tip,
              new_count,new_head,new_history,new_tip):
    """Create the deterministic UNSIGNED statement for independent signing."""
    if role not in ROLES:
        raise LatestHeadConflict('invalid enrolled notary role')
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise LatestHeadConflict('invalid latest-head scope')
    _digest(challenge,HEX32)
    if (type(old_count) is not int or type(new_count) is not int
            or not 0 <= old_count < new_count <= MAX_COUNT):
        raise LatestHeadConflict('notary must endorse strict head advancement')
    for value in (old_head,old_history,old_tip,new_head,new_history,new_tip):
        _digest(value)
    return {
        'schema':SCHEMA,'notary_role':role,'checkpoint_scope':scope,
        'challenge_nonce':challenge,
        'old_event_count':old_count,'old_head_sha256':old_head,
        'old_history_sha256':old_history,
        'old_latest_witness_sha256':old_tip,
        'new_event_count':new_count,'new_head_sha256':new_head,
        'new_history_sha256':new_history,
        'new_latest_witness_sha256':new_tip,
        'witness_fence_retirement_authorized':False,
    }


def bundle_digest(signed_a,signed_b):
    if (type(signed_a) is not bytes or type(signed_b) is not bytes
            or not 0 < len(signed_a) <= MAX_SIGNED
            or not 0 < len(signed_b) <= MAX_SIGNED):
        raise LatestHeadConflict('invalid signed latest-head envelope size')
    item = {
        'schema':SCHEMA,
        'notary_a_signed_sha256':hashlib.sha256(signed_a).hexdigest(),
        'notary_b_signed_sha256':hashlib.sha256(signed_b).hexdigest(),
    }
    return hashlib.sha256(BUNDLE_DOMAIN+_canonical(item)).hexdigest()


def verify(old_a,old_b,old_count,old_head,old_history,old_pin,old_tip,
           new_a,new_b,new_count,new_head,new_history,new_pin,new_tip,
           witness_public_a,witness_public_pin_a,
           witness_public_b,witness_public_pin_b,
           signed_notary_a,notary_public_a,notary_public_pin_a,
           signed_notary_b,notary_public_b,notary_public_pin_b, *,
           scope,external_challenge,external_latest_count,
           external_latest_head,external_latest_history,
           external_latest_witness,external_notary_bundle):
    """Full transition plus exact two-notary current head witness, read-only."""
    _digest(external_challenge,HEX32)
    for v in (external_latest_head,external_latest_history,
              external_latest_witness,external_notary_bundle):
        _digest(v)
    if type(external_latest_count) is not int:
        raise LatestHeadConflict('invalid external latest event count')
    if (external_latest_count != new_count
            or not hmac.compare_digest(external_latest_head,new_head)
            or not hmac.compare_digest(external_latest_history,new_pin)
            or not hmac.compare_digest(external_latest_witness,new_tip)):
        raise LatestHeadConflict('presented new state is stale vs external latest tuple')
    for public_pin in (notary_public_pin_a,notary_public_pin_b):
        _digest(public_pin)
    if (hmac.compare_digest(notary_public_pin_a,notary_public_pin_b)
            or hmac.compare_digest(
                _public_key_identity(notary_public_a),
                _public_key_identity(notary_public_b))):
        raise LatestHeadConflict('two notaries share the same enrolled public key')

    signed_claims=[]
    for role,raw,key,pin in (
            (ROLES[0],signed_notary_a,notary_public_a,notary_public_pin_a),
            (ROLES[1],signed_notary_b,notary_public_b,notary_public_pin_b)):
        body = _signed(raw,SCHEMA,DOMAIN,pin,key)
        if type(body) is not dict or set(body) != FIELDS:
            raise LatestHeadConflict('unexpected signed notary fields')
        expected = make_body(
            role,scope,external_challenge,old_count,old_head,old_pin,old_tip,
            new_count,new_head,new_pin,new_tip)
        if body != expected:
            raise LatestHeadConflict('notary signed a different challenged head')
        signed_claims.append(body)
    if {k:v for k,v in signed_claims[0].items() if k!='notary_role'} != {
            k:v for k,v in signed_claims[1].items() if k!='notary_role'}:
        raise LatestHeadConflict('notary statements conflict')

    candidate=bundle_digest(signed_notary_a,signed_notary_b)
    if not hmac.compare_digest(candidate,external_notary_bundle):
        raise LatestHeadConflict('signed notary bundle differs from external pin')

    validated=verify_transition(
        old_a,old_b,old_count,old_head,old_history,old_pin,old_tip,
        new_a,new_b,new_count,new_head,new_history,new_pin,new_tip,
        witness_public_a,witness_public_pin_a,
        witness_public_b,witness_public_pin_b,scope=scope)
    if validated['witness_fence_retirement_authorized'] is not False:
        raise LatestHeadConflict('unexpected release authorization')
    return {
        'schema':REPORT_SCHEMA,
        'exact_external_current_tuple_matches_signed_new_head':True,
        'external_challenge_authenticated_by_two_notaries':True,
        'distinct_notary_ed25519_keys_verified':True,
        'signed_bundle_matches_independent_pin':True,
        'full_signed_prefix_transition_verified':True,
        'notary_bundle_sha256':candidate,
        'new_event_count':new_count,
        'new_head_sha256':new_head,
        'actual_external_challenge_freshness_proved':False,
        'trusted_current_external_pin_storage_proved':False,
        'old_pins_plus_old_challenge_replay_excluded':False,
        'global_monotonic_counter_proved':False,
        'independent_physical_notary_control_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for stage in ('old','new'):
        p.add_argument(stage+'_mirror_a',type=Path)
        p.add_argument(stage+'_mirror_b',type=Path)
        p.add_argument(stage+'_history',type=Path)
        p.add_argument('--'+stage+'-count',required=True,type=int)
        p.add_argument('--'+stage+'-head',required=True)
        p.add_argument('--'+stage+'-history-sha256',required=True)
        p.add_argument('--'+stage+'-latest-witness-sha256',required=True)
    for role in ('a','b'):
        p.add_argument('--witness-admin-'+role+'-public',type=Path,required=True)
        p.add_argument('--witness-admin-'+role+'-public-pin',required=True)
        p.add_argument('--notary-'+role+'-signed',type=Path,required=True)
        p.add_argument('--notary-'+role+'-public',type=Path,required=True)
        p.add_argument('--notary-'+role+'-public-pin',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--external-challenge-nonce',required=True)
    p.add_argument('--external-latest-count',type=int,required=True)
    p.add_argument('--external-latest-head',required=True)
    p.add_argument('--external-latest-history-sha256',required=True)
    p.add_argument('--external-latest-witness-sha256',required=True)
    p.add_argument('--external-notary-bundle-sha256',required=True)
    a=p.parse_args(argv)
    report={'schema':REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        read=lambda path,size:_read_limited(_private_regular_file(path),size)
        report.update(verify(
            a.old_mirror_a,a.old_mirror_b,
            a.old_count,a.old_head,read(a.old_history,MAX_ARCHIVE),
            a.old_history_sha256,a.old_latest_witness_sha256,
            a.new_mirror_a,a.new_mirror_b,
            a.new_count,a.new_head,read(a.new_history,MAX_ARCHIVE),
            a.new_history_sha256,a.new_latest_witness_sha256,
            a.witness_admin_a_public,a.witness_admin_a_public_pin,
            a.witness_admin_b_public,a.witness_admin_b_public_pin,
            read(a.notary_a_signed,MAX_SIGNED),
            a.notary_a_public,a.notary_a_public_pin,
            read(a.notary_b_signed,MAX_SIGNED),
            a.notary_b_public,a.notary_b_public_pin,
            scope=a.scope,
            external_challenge=a.external_challenge_nonce,
            external_latest_count=a.external_latest_count,
            external_latest_head=a.external_latest_head,
            external_latest_history=a.external_latest_history_sha256,
            external_latest_witness=a.external_latest_witness_sha256,
            external_notary_bundle=a.external_notary_bundle_sha256))
        status=0
    except (LatestHeadConflict,TransitionConflict,ValueError):
        report['challenged_latest_head_conflict']=True
        status=1
    except (OSError,TypeError,KeyError,IndexError):
        report['valid_input']=False
        status=2
    print(json.dumps(report,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
