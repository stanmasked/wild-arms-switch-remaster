"""Stage 264B: two-authority fresh recheck after checkpoint keeper reconnect.

Read-only comparison against independent operator pins, an archived complete
signed pair, and two fresh challenge-bound source responses. No trust in an
unprovisioned source or local keeper independence is implied.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

try:
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from . import audit_record_witness_publication_cas_reconciliation as recovery
    from . import audit_record_witness_publication_two_source as dual
    from . import audit_record_witness_publication_live_source as live
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_replay_head_checkpoint import HEX32, TAG, _public_key_identity
except ImportError:
    import audit_record_witness_publication_checkpoint_cas as cas
    import audit_record_witness_publication_cas_reconciliation as recovery
    import audit_record_witness_publication_two_source as dual
    import audit_record_witness_publication_live_source as live
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_replay_head_checkpoint import HEX32, TAG, _public_key_identity

REPORT_SCHEMA = 'wild-arms-ps1-live-head-reconnect-cross-check-v1'


class ReconnectConflict(cas.CheckpointCASConflict):
    """The keeper and enrolled online authorities do not agree."""


def _enrollment(source_a, source_b, notaries, scope):
    if (type(source_a) is not dict or set(source_a) != dual.SOURCE_KEYS
            or type(source_b) is not dict or set(source_b) != dual.SOURCE_KEYS
            or type(notaries) is not dict or set(notaries) != dual.NOTARY_KEYS
            or type(scope) is not str or not TAG.fullmatch(scope)):
        raise ReconnectConflict('invalid enrollment shape')
    for source in (source_a,source_b):
        live.validate_url(source['source_url'])
        if (type(source['authority_id']) is not str
                or not TAG.fullmatch(source['authority_id'])):
            raise ReconnectConflict('invalid enrolled authority identity')
        cas.digest(source['authority_pin'])
    if (source_a['authority_id'] == source_b['authority_id']
            or urlsplit(source_a['source_url']).hostname ==
               urlsplit(source_b['source_url']).hostname):
        raise ReconnectConflict('authorities share identity or DNS host')
    pairs = [
        (source_a['authority_public'],source_a['authority_pin']),
        (source_b['authority_public'],source_b['authority_pin']),
        (notaries['notary_a_public'],notaries['notary_a_pin']),
        (notaries['notary_b_public'],notaries['notary_b_pin']),
    ]
    identities=[]
    for key,pin in pairs:
        cas.digest(pin)
        pem = _read_limited(_private_regular_file(key),4096)
        if not hmac.compare_digest(hashlib.sha256(pem).hexdigest(),pin):
            raise ReconnectConflict('independently enrolled PEM material changed')
        identities.append(_public_key_identity(key))
    if len(set(identities)) != 4:
        raise ReconnectConflict('authority and notary keys are not distinct')


def recheck(path, archived_signed_a, archived_signed_b, *,
            archived_nonce_a, archived_nonce_b,
            source_a, source_b, notaries, scope, expected,
            expected_generation, expected_pair_pin, expected_event_head,
            fetcher=None, challenges=None):
    """Observe matching keeper + archived pair + live pair, without mutation."""
    if type(expected) is not dict or set(expected) != dual.STATE_KEYS:
        raise ReconnectConflict('invalid independently trusted head tuple')
    cas.number(expected['count'],live.MAX_COUNT,'expected event count')
    for name in ('head','history','witness','bundle'):
        cas.digest(expected[name])
    cas.number(expected_generation,cas.MAX_COUNT,'expected generation')
    cas.digest(expected_pair_pin)
    cas.digest(expected_event_head)
    _enrollment(source_a,source_b,notaries,scope)
    if (type(archived_nonce_a) is not str or not HEX32.fullmatch(archived_nonce_a)
            or type(archived_nonce_b) is not str or not HEX32.fullmatch(archived_nonce_b)
            or archived_nonce_a == archived_nonce_b):
        raise ReconnectConflict('invalid archived source challenges')
    prior_digest=dual.checkpoint_digest(
        archived_signed_a,archived_signed_b,scope=scope,
        source_a_pin=source_a['authority_pin'],
        source_b_pin=source_b['authority_pin'])
    if not hmac.compare_digest(prior_digest,expected_pair_pin):
        raise ReconnectConflict('archived signed-pair digest not externally trusted')

    first_state, first_rows=recovery._snapshot(path)
    if (first_state[1] != scope or first_state[0] != expected_generation
            or not hmac.compare_digest(first_state[2],expected_pair_pin)
            or not hmac.compare_digest(first_state[6],expected_event_head)
            or first_state[3] != expected['count']):
        raise ReconnectConflict('keeper latest head disagrees with external pins')
    floor_a,floor_b=first_state[4],first_state[5]
    for source,raw,nonce,floor in (
            (source_a,archived_signed_a,archived_nonce_a,floor_a),
            (source_b,archived_signed_b,archived_nonce_b,floor_b)):
        seen=live.verify_receipt(
            raw,challenge=nonce,
            **dual._source_args(source,notaries,scope,expected,floor))
        if seen['authority_sequence'] != floor:
            raise ReconnectConflict('archived source sequence differs from keeper')
    if challenges is None:
        challenges=(secrets.token_hex(16),secrets.token_hex(16))
    if (type(challenges) not in (tuple,list) or len(challenges) != 2
            or any(type(c) is not str or not HEX32.fullmatch(c) for c in challenges)
            or len(set(tuple(challenges)+(archived_nonce_a,archived_nonce_b))) != 4):
        raise ReconnectConflict('fresh challenges not distinct from archived challenges')
    if fetcher is None:
        fetcher=live.fetch_live_receipt
    reports=[]
    for source,nonce,floor in (
            (source_a,challenges[0],floor_a),
            (source_b,challenges[1],floor_b)):
        raw=fetcher(source['source_url'],scope,nonce)
        reports.append(live.verify_receipt(
            raw,challenge=nonce,
            **dual._source_args(source,notaries,scope,expected,floor)))
    second_state, second_rows=recovery._snapshot(path)
    if second_state != first_state or second_rows != first_rows:
        raise ReconnectConflict('keeper changed during external source recheck')
    return {
        'schema': REPORT_SCHEMA,
        'two_keeper_snapshots_match_during_source_recheck':True,
        'keeper_matches_independently_supplied_head':True,
        'archived_ed25519_pair_matches_committed_digest':True,
        'four_distinct_pinned_authority_and_notary_keys':True,
        'two_new_distinct_challenge_ed25519_responses_valid':True,
        'fresh_online_sources_agree_with_pinned_stage_263w_tuple':True,
        'source_sequences_did_not_rollback':True,
        'checkpoint_generation': expected_generation,
        'checkpoint_event_count': expected['count'],
        'checkpoint_pair_sha256':expected_pair_pin,
        'checkpoint_event_head_sha256':expected_event_head,
        'fresh_source_a_sequence': reports[0]['authority_sequence'],
        'fresh_source_b_sequence': reports[1]['authority_sequence'],
        'fresh_signed_envelopes_equal_archived_envelopes_required':False,
        'external_monotonic_pin_storage_proved':False,
        'physical_authority_independence_proved':False,
        'remote_global_latest_head_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('database',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--expected-generation',type=int,required=True)
    p.add_argument('--expected-pair-pin',required=True)
    p.add_argument('--expected-event-head',required=True)
    p.add_argument('--expected-count',type=int,required=True)
    for key in ('head','history','witness','bundle'):
        p.add_argument('--expected-'+key+'-sha256',required=True)
    for name in ('a','b'):
        p.add_argument('--source-'+name+'-url',required=True)
        p.add_argument('--source-'+name+'-id',required=True)
        p.add_argument('--source-'+name+'-public',type=Path,required=True)
        p.add_argument('--source-'+name+'-pin',required=True)
        p.add_argument('--archived-'+name+'-signed',type=Path,required=True)
        p.add_argument('--archived-'+name+'-nonce',required=True)
        p.add_argument('--notary-'+name+'-public',type=Path,required=True)
        p.add_argument('--notary-'+name+'-pin',required=True)
    a=p.parse_args(argv)
    source=lambda name:{
        'source_url':getattr(a,'source_'+name+'_url'),
        'authority_id':getattr(a,'source_'+name+'_id'),
        'authority_public':getattr(a,'source_'+name+'_public'),
        'authority_pin':getattr(a,'source_'+name+'_pin'),
    }
    current={'count':a.expected_count}
    current.update({key:getattr(a,'expected_'+key+'_sha256')
                    for key in ('head','history','witness','bundle')})
    report={'schema':REPORT_SCHEMA,
            'automatic_cas_retry_authorized':False,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        result=recheck(a.database,
            _read_limited(_private_regular_file(a.archived_a_signed),
                          live.MAX_RESPONSE),
            _read_limited(_private_regular_file(a.archived_b_signed),
                          live.MAX_RESPONSE),
            archived_nonce_a=a.archived_a_nonce,
            archived_nonce_b=a.archived_b_nonce,
            source_a=source('a'),source_b=source('b'),
            notaries={
                'notary_a_public':a.notary_a_public,
                'notary_a_pin':a.notary_a_pin,
                'notary_b_public':a.notary_b_public,
                'notary_b_pin':a.notary_b_pin,
            },scope=a.scope,expected=current,
            expected_generation=a.expected_generation,
            expected_pair_pin=a.expected_pair_pin,
            expected_event_head=a.expected_event_head)
        report.update(result)
        status=0
    except live.LiveSourceUnavailable:
        report['source_unavailable']=True
        status=2
    except (ReconnectConflict,cas.CheckpointCASConflict,
            live.LiveSourceConflict,dual.DualSourceConflict,
            ValueError,OSError,TypeError,KeyError,IndexError):
        report['reconnect_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
