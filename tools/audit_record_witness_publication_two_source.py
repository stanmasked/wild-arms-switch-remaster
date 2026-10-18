"""Stage 263Y: two-source, externally pinned signed-head advancement claim.

Verify TWO old signed Stage-263X authority replies under one externally
retained checkpoint SHA-256, then make TWO fresh HTTPS challenges and demand
strict progress in both sequence numbers and publication event count.
No authority servers or external pin stores are deployed by this module.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_replay_head_checkpoint import (
        HEX32, HEX64, TAG, _public_key_identity,
    )
    from . import audit_record_witness_publication_live_source as live
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_replay_head_checkpoint import (
        HEX32, HEX64, TAG, _public_key_identity,
    )
    import audit_record_witness_publication_live_source as live

SCHEMA = 'wild-arms-ps1-dual-source-head-transition-v1'
REPORT_SCHEMA = 'wild-arms-ps1-dual-source-head-transition-report-v1'
DOMAIN = b'wild-arms-ps1-dual-source-head-transition-v1\x00'
STATE_KEYS = {'count', 'head', 'history', 'witness', 'bundle'}
OLD_KEYS = STATE_KEYS | {'challenge_a','challenge_b','sequence_a','sequence_b'}
SOURCE_KEYS = {'source_url','authority_id','authority_public','authority_pin'}
NOTARY_KEYS = {'notary_a_public','notary_a_pin','notary_b_public','notary_b_pin'}


class DualSourceConflict(ValueError):
    """External checkpoint, source independence or progression conflict."""


def checkpoint_digest(signed_a, signed_b, *, scope, source_a_pin, source_b_pin):
    """Portable domain-separated digest; must be retained outside both hosts."""
    if (type(scope) is not str or not TAG.fullmatch(scope)
            or any(type(p) is not str or not HEX64.fullmatch(p)
                   for p in (source_a_pin,source_b_pin))
            or type(signed_a) is not bytes or type(signed_b) is not bytes
            or not 0 < len(signed_a) <= live.MAX_RESPONSE
            or not 0 < len(signed_b) <= live.MAX_RESPONSE):
        raise DualSourceConflict('invalid external two-source checkpoint inputs')
    return hashlib.sha256(DOMAIN + _canonical({
        'schema': SCHEMA, 'checkpoint_scope': scope,
        'authority_a_public_pin': source_a_pin,
        'authority_b_public_pin': source_b_pin,
        'source_a_envelope_sha256': hashlib.sha256(signed_a).hexdigest(),
        'source_b_envelope_sha256': hashlib.sha256(signed_b).hexdigest(),
    })).hexdigest()


def _source_args(source, notaries, scope, state, floor):
    return dict(source, **notaries, scope=scope,
                minimum_sequence=floor,
                expected_count=state['count'], expected_head=state['head'],
                expected_history=state['history'],
                expected_witness=state['witness'],
                expected_bundle=state['bundle'])


def verify(old_signed_a, old_signed_b, *, old_checkpoint_pin,
           old, current, source_a, source_b, notaries, scope,
           fetcher=None, challenges=None):
    """Compare signed prior pair to two separately challenged current heads."""
    if (type(old) is not dict or set(old) != OLD_KEYS
            or type(current) is not dict or set(current) != STATE_KEYS
            or type(source_a) is not dict or set(source_a) != SOURCE_KEYS
            or type(source_b) is not dict or set(source_b) != SOURCE_KEYS
            or type(notaries) is not dict or set(notaries) != NOTARY_KEYS):
        raise DualSourceConflict('invalid enrolled two-source input shape')
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise DualSourceConflict('invalid two-source checkpoint scope')
    for name in ('a','b'):
        if (type(old['challenge_'+name]) is not str
                or not HEX32.fullmatch(old['challenge_'+name])
                or type(old['sequence_'+name]) is not int
                or not 0 <= old['sequence_'+name] < live.MAX_SEQUENCE):
            raise DualSourceConflict('invalid previous challenge/sequence')
    if old['challenge_a'] == old['challenge_b']:
        raise DualSourceConflict('old source challenges must be different')
    if (type(old['count']) is not int or type(current['count']) is not int
            or not 0 <= old['count'] < current['count'] <= live.MAX_COUNT):
        raise DualSourceConflict('current event count must advance strictly')
    for state in (old,current):
        for key in ('head','history','witness','bundle'):
            if type(state[key]) is not str or not HEX64.fullmatch(state[key]):
                raise DualSourceConflict('invalid publication SHA-256 digest')
    if all(old[k] == current[k] for k in ('head','history','witness','bundle')):
        raise DualSourceConflict('unchanged head cannot represent advancement')
    for source in (source_a,source_b):
        live.validate_url(source['source_url'])
        if (type(source['authority_id']) is not str
                or not TAG.fullmatch(source['authority_id'])
                or type(source['authority_pin']) is not str
                or not HEX64.fullmatch(source['authority_pin'])):
            raise DualSourceConflict('invalid enrolled authority')
    if (source_a['authority_id'] == source_b['authority_id']
            or urlsplit(source_a['source_url']).hostname ==
               urlsplit(source_b['source_url']).hostname):
        raise DualSourceConflict('authority identity or DNS host is shared')

    # Four independently pinned public keys must be distinct by DER,
    # including when the same key is re-encoded as a different PEM.
    keypairs = [(source_a['authority_public'],source_a['authority_pin']),
                (source_b['authority_public'],source_b['authority_pin']),
                (notaries['notary_a_public'],notaries['notary_a_pin']),
                (notaries['notary_b_public'],notaries['notary_b_pin'])]
    identities = []
    for path,pin in keypairs:
        if type(pin) is not str or not HEX64.fullmatch(pin):
            raise DualSourceConflict('invalid enrolled PEM pin')
        data = _read_limited(_private_regular_file(path),4096)
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(),pin):
            raise DualSourceConflict('changed enrolled PEM material')
        identities.append(_public_key_identity(path))
    if len(set(identities)) != 4:
        raise DualSourceConflict('two authorities and notaries must use four keys')

    candidate = checkpoint_digest(old_signed_a,old_signed_b,
        scope=scope, source_a_pin=source_a['authority_pin'],
        source_b_pin=source_b['authority_pin'])
    if (type(old_checkpoint_pin) is not str
            or not HEX64.fullmatch(old_checkpoint_pin)
            or not hmac.compare_digest(candidate,old_checkpoint_pin)):
        raise DualSourceConflict('previous signed source pair lacks external pin')
    prior = []
    for name,raw,source in (('a',old_signed_a,source_a),
                            ('b',old_signed_b,source_b)):
        validated=live.verify_receipt(raw,challenge=old['challenge_'+name],
            **_source_args(source,notaries,scope,old,old['sequence_'+name]))
        if validated['authority_sequence'] != old['sequence_'+name]:
            raise DualSourceConflict('prior signed sequence changed')
        prior.append(validated)
    if challenges is None:
        challenges = (secrets.token_hex(16),secrets.token_hex(16))
    if (type(challenges) not in (tuple,list) or len(challenges) != 2
            or any(type(v) is not str or not HEX32.fullmatch(v)
                   for v in challenges)
            or len(set(challenges + (old['challenge_a'],old['challenge_b']))) != 4):
        raise DualSourceConflict('new challenges must differ from all prior ones')
    if fetcher is None:
        fetcher = live.fetch_live_receipt
    new_raw = []
    new_report = []
    for source, nonce, minimum in (
            (source_a,challenges[0],old['sequence_a']+1),
            (source_b,challenges[1],old['sequence_b']+1)):
        response=fetcher(source['source_url'],scope,nonce)
        new_raw.append(response)
        new_report.append(live.verify_receipt(
            response, challenge=nonce,
            **_source_args(source,notaries,scope,current,minimum)))
    proposed_checkpoint = checkpoint_digest(
        new_raw[0],new_raw[1],scope=scope,
        source_a_pin=source_a['authority_pin'],
        source_b_pin=source_b['authority_pin'])
    return {
        'schema': REPORT_SCHEMA,
        'two_old_ed25519_authority_claims_verified': True,
        'old_pair_matches_independently_supplied_checkpoint': True,
        'two_distinct_authority_keys_and_dns_hosts_checked': True,
        'two_new_challenge_bound_ed25519_claims_verified': True,
        'each_authority_sequence_strictly_advanced': True,
        'new_event_count_strictly_advanced': True,
        'both_new_claims_match_expected_stage_263w_tuple': True,
        'previous_checkpoint_sha256': candidate,
        'proposed_new_checkpoint_sha256': proposed_checkpoint,
        'new_event_count': current['count'],
        'new_head_sha256': current['head'],
        'source_a_new_sequence': new_report[0]['authority_sequence'],
        'source_b_new_sequence': new_report[1]['authority_sequence'],
        'external_store_commit_or_readback_proved': False,
        'physical_or_administrative_independence_proved': False,
        'global_latest_head_proved': False,
        'compromised_both_sources_rollback_excluded': False,
        'full_stage_263v_transition_rechecked_here': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('a','b'):
        p.add_argument('--source-'+name+'-url',required=True)
        p.add_argument('--source-'+name+'-id',required=True)
        p.add_argument('--source-'+name+'-public',type=Path,required=True)
        p.add_argument('--source-'+name+'-pin',required=True)
        p.add_argument('--old-'+name+'-signed',type=Path,required=True)
        p.add_argument('--old-'+name+'-challenge',required=True)
        p.add_argument('--old-'+name+'-sequence',type=int,required=True)
    for name in ('a','b'):
        p.add_argument('--notary-'+name+'-public',type=Path,required=True)
        p.add_argument('--notary-'+name+'-pin',required=True)
    for name in ('old','new'):
        p.add_argument('--'+name+'-count',type=int,required=True)
        for key in ('head','history','witness','bundle'):
            p.add_argument('--'+name+'-'+key+'-sha256',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--old-checkpoint-sha256',required=True)
    a=p.parse_args(argv)
    source=lambda role:{
        'source_url':getattr(a,'source_'+role+'_url'),
        'authority_id':getattr(a,'source_'+role+'_id'),
        'authority_public':getattr(a,'source_'+role+'_public'),
        'authority_pin':getattr(a,'source_'+role+'_pin'),
    }
    state=lambda name:{
        'count':getattr(a,name+'_count'),
        **{key:getattr(a,name+'_'+key+'_sha256')
           for key in ('head','history','witness','bundle')},
    }
    old=state('old')
    for name in ('a','b'):
        old['challenge_'+name]=getattr(a,'old_'+name+'_challenge')
        old['sequence_'+name]=getattr(a,'old_'+name+'_sequence')
    report={'schema':REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        report.update(verify(
            _read_limited(_private_regular_file(a.old_a_signed),
                          live.MAX_RESPONSE),
            _read_limited(_private_regular_file(a.old_b_signed),
                          live.MAX_RESPONSE),
            old_checkpoint_pin=a.old_checkpoint_sha256,
            old=old,current=state('new'),source_a=source('a'),
            source_b=source('b'),scope=a.scope,
            notaries={
                'notary_a_public':a.notary_a_public,
                'notary_a_pin':a.notary_a_pin,
                'notary_b_public':a.notary_b_public,
                'notary_b_pin':a.notary_b_pin,
            }))
        status=0
    except live.LiveSourceUnavailable:
        report['authority_unavailable']=True
        status=2
    except (DualSourceConflict,live.LiveSourceConflict,
            ValueError,OSError,TypeError,KeyError,IndexError):
        report['dual_source_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
