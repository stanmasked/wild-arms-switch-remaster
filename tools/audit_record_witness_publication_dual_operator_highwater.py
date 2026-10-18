"""Stage 264C: read-only historical high-watermark rollback audit.

Two separately signed offline operator certificates bind independently retained
generations/chain heads. A keeper (and BOTH live sources) cannot regress below
either trust anchor without a mismatch -- assuming the caller really retains
the latest external signed certificate pins and sequence floors.
No external operators/services are provisioned by this reference module.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_witness_replay_head_checkpoint import TAG, _public_key_identity
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from . import audit_record_witness_publication_cas_reconciliation as recovery
    from . import audit_record_witness_publication_reconnect_crosscheck as reconnect
except ImportError:
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_witness_replay_head_checkpoint import TAG, _public_key_identity
    import audit_record_witness_publication_checkpoint_cas as cas
    import audit_record_witness_publication_cas_reconciliation as recovery
    import audit_record_witness_publication_reconnect_crosscheck as reconnect

SCHEMA='wild-arms-ps1-dual-operator-checkpoint-highwater-v1'
REPORT_SCHEMA='wild-arms-ps1-dual-operator-checkpoint-highwater-report-v1'
DOMAIN=b'wild-arms-ps1-dual-operator-checkpoint-highwater-v1\x00'
MAX_CERT=2048
KEYS={'schema','operator_id','checkpoint_scope','seal_sequence',
      'generation','event_head_sha256','pair_sha256','event_count',
      'source_a_sequence','source_b_sequence',
      'witness_fence_retirement_authorized'}


class HighwaterConflict(cas.CheckpointCASConflict):
    """The keeper or trusted historical floor cannot be reconciled."""


def _key_identity(public, pin):
    cas.digest(pin)
    data=_read_limited(_private_regular_file(public),4096)
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(),pin):
        raise HighwaterConflict('changed externally enrolled public PEM')
    return _public_key_identity(public)


def _certificate(raw, public, pin, external_sha256, min_seal_sequence,
                 expected_id, scope):
    cas.digest(external_sha256)
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_CERT
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),
                                       external_sha256)):
        raise HighwaterConflict('signed watermark not independently pinned')
    if type(expected_id) is not str or not TAG.fullmatch(expected_id):
        raise HighwaterConflict('invalid independent operator identifier')
    cas.number(min_seal_sequence,cas.MAX_SEQUENCE,'external certificate floor')
    body=_signed(raw,SCHEMA,DOMAIN,pin,public)
    if (type(body) is not dict or set(body) != KEYS
            or body['schema'] != SCHEMA
            or body['operator_id'] != expected_id
            or body['checkpoint_scope'] != scope
            or body['witness_fence_retirement_authorized'] is not False):
        raise HighwaterConflict('signed high-watermark identity or policy mismatch')
    cas.number(body['seal_sequence'],cas.MAX_SEQUENCE,'seal sequence')
    if body['seal_sequence'] < min_seal_sequence:
        raise HighwaterConflict('signed observer seal sequence rolled back')
    for field in ('generation','event_count'):
        cas.number(body[field],cas.MAX_COUNT,field)
    for field in ('source_a_sequence','source_b_sequence'):
        cas.number(body[field],cas.MAX_SEQUENCE,field)
    cas.digest(body['event_head_sha256'])
    cas.digest(body['pair_sha256'])
    return body


def verify(path, raw_a, raw_b, *,
           scope, operator_a_id, operator_b_id,
           operator_a_public, operator_a_pin,
           operator_b_public, operator_b_pin,
           external_a_sha256, external_b_sha256,
           external_a_sequence_floor, external_b_sequence_floor,
           expected_generation, expected_pair_pin, expected_event_head,
           excluded_pinned_public_keys=()):
    """Verify two externally pinned certificates and full local keeper chain.

    Excluded keypairs bind separately enrolled authority/notary public keys
    when used alongside the Stage 264B dual-source recheck.
    """
    if (type(scope) is not str or not TAG.fullmatch(scope)
            or type(excluded_pinned_public_keys) not in (list,tuple)
            or (operator_a_id == operator_b_id)):
        raise HighwaterConflict('bad dual-operator enrollment')
    seen=[
        _key_identity(operator_a_public,operator_a_pin),
        _key_identity(operator_b_public,operator_b_pin),
    ]
    for pair in excluded_pinned_public_keys:
        if type(pair) not in (tuple,list) or len(pair) != 2:
            raise HighwaterConflict('invalid excluded source identity')
        seen.append(_key_identity(pair[0],pair[1]))
    if len(set(seen)) != len(seen):
        raise HighwaterConflict('operator keys overlap other enrolled roles')
    body_a=_certificate(raw_a,operator_a_public,operator_a_pin,
                        external_a_sha256,external_a_sequence_floor,
                        operator_a_id,scope)
    body_b=_certificate(raw_b,operator_b_public,operator_b_pin,
                        external_b_sha256,external_b_sequence_floor,
                        operator_b_id,scope)
    # Two independently retained operator certificates must describe the
    # SAME historical floor. Otherwise there is no quorum agreement.
    history_fields=('generation','event_head_sha256','pair_sha256',
                    'event_count','source_a_sequence','source_b_sequence')
    if any(body_a[f] != body_b[f] for f in history_fields):
        raise HighwaterConflict('two external operator checkpoints disagree')
    cas.number(expected_generation,cas.MAX_COUNT,'expected generation')
    cas.digest(expected_pair_pin)
    cas.digest(expected_event_head)
    first,rows_a=recovery._snapshot(path)
    second,rows_b=recovery._snapshot(path)
    if first != second or rows_a != rows_b or first[1] != scope:
        raise HighwaterConflict('keeper snapshot changed or scope differs')
    if (first[0] != expected_generation
            or not hmac.compare_digest(first[2],expected_pair_pin)
            or not hmac.compare_digest(first[6],expected_event_head)):
        raise HighwaterConflict('keeper head differs from externally supplied expectation')
    anchor_gen=body_a['generation']
    if first[0] < anchor_gen or anchor_gen >= len(rows_b):
        raise HighwaterConflict('keeper rolled back behind independently signed floor')
    anchor=rows_b[anchor_gen]
    if (anchor[0] != anchor_gen or anchor[3] != body_a['pair_sha256']
            or anchor[8] != body_a['event_head_sha256']
            or anchor[4] != body_a['event_count']
            or anchor[5] != body_a['source_a_sequence']
            or anchor[6] != body_a['source_b_sequence']):
        raise HighwaterConflict('keeper history not a continuation of signed floor')
    if (first[3] < body_a['event_count']
            or first[4] < body_a['source_a_sequence']
            or first[5] < body_a['source_b_sequence']):
        raise HighwaterConflict('keeper counters rolled back below signed floor')
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_pinned_operator_ed25519_seals_verified':True,
        'both_operators_agree_on_historical_floor':True,
        'keeper_history_includes_exact_signed_anchor':True,
        'keeper_head_meets_external_signed_generation_floor':True,
        'both_operator_seal_sequences_meet_external_floors':True,
        'signed_floor_generation':anchor_gen,
        'observed_head_generation':first[0],
        'observed_head_sha256':first[6],
        'historical_pair_sha256':body_a['pair_sha256'],
        'two_signed_observer_certificates_are_from_deployed_external_hosts_proved':False,
        'externally_retained_pins_are_latest_proved':False,
        'coordinated_rollback_with_compromised_external_pins_excluded':False,
        'global_latest_publication_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def verify_with_live_sources(path, raw_a, raw_b, *,
                             highwater_args, reconnect_args):
    """Run signed historical floors, then fresh two-source recheck, then floors.

    A successful result is still conditional on out-of-band trust of the
    enrolled certificate hash pins and both independent signing authorities.
    """
    if type(highwater_args) is not dict or type(reconnect_args) is not dict:
        raise HighwaterConflict('missing independent live/high-watermark inputs')
    # Always bind the two additional observer keys to ALL four live roles.
    # The caller must not be able to silently omit cross-role independence.
    try:
        four = tuple((item['authority_public'],item['authority_pin'])
                     for item in (reconnect_args['source_a'],
                                  reconnect_args['source_b'])) + (
            (reconnect_args['notaries']['notary_a_public'],
             reconnect_args['notaries']['notary_a_pin']),
            (reconnect_args['notaries']['notary_b_public'],
             reconnect_args['notaries']['notary_b_pin']),
        )
        declared=tuple(highwater_args.get('excluded_pinned_public_keys',()))
        if declared and declared != four:
            raise HighwaterConflict('combined verifier enrolled roles differ')
        if (highwater_args['scope'] != reconnect_args['scope']
                or highwater_args['expected_generation'] !=
                   reconnect_args['expected_generation']
                or highwater_args['expected_pair_pin'] !=
                   reconnect_args['expected_pair_pin']
                or highwater_args['expected_event_head'] !=
                   reconnect_args['expected_event_head']):
            raise HighwaterConflict('independent high-watermark and live pins differ')
    except (KeyError,TypeError) as exc:
        raise HighwaterConflict('missing combined verifier enrollment') from exc
    bound=dict(highwater_args,excluded_pinned_public_keys=four)
    prior=verify(path,raw_a,raw_b,**bound)
    current=reconnect.recheck(path,**reconnect_args)
    after=verify(path,raw_a,raw_b,**bound)
    if prior != after:
        raise HighwaterConflict('historical floor changed during dual-source crosscheck')
    if current['checkpoint_generation'] != after['observed_head_generation']:
        raise HighwaterConflict('live recheck observed different keeper generation')
    if current['checkpoint_event_head_sha256'] != after['observed_head_sha256']:
        raise HighwaterConflict('live recheck observed different keeper head')
    return {
        **after,
        'fresh_dual_source_checkpoint_agrees_with_signed_historical_floor':True,
        'fresh_authority_a_sequence':current['fresh_source_a_sequence'],
        'fresh_authority_b_sequence':current['fresh_source_b_sequence'],
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('database',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--expected-generation',required=True,type=int)
    p.add_argument('--expected-pair-pin',required=True)
    p.add_argument('--expected-event-head',required=True)
    for name in ('a','b'):
        p.add_argument('--operator-'+name+'-id',required=True)
        p.add_argument('--operator-'+name+'-public',type=Path,required=True)
        p.add_argument('--operator-'+name+'-pin',required=True)
        p.add_argument('--signed-'+name+'-checkpoint',type=Path,required=True)
        p.add_argument('--external-'+name+'-sha256',required=True)
        p.add_argument('--external-'+name+'-sequence-floor',required=True,type=int)
    a=p.parse_args(argv)
    report={'schema':REPORT_SCHEMA,
            'automatic_cas_retry_authorized':False,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        report.update(verify(a.database,
            _read_limited(_private_regular_file(a.signed_a_checkpoint),MAX_CERT),
            _read_limited(_private_regular_file(a.signed_b_checkpoint),MAX_CERT),
            scope=a.scope,
            operator_a_id=a.operator_a_id,
            operator_b_id=a.operator_b_id,
            operator_a_public=a.operator_a_public,
            operator_a_pin=a.operator_a_pin,
            operator_b_public=a.operator_b_public,
            operator_b_pin=a.operator_b_pin,
            external_a_sha256=a.external_a_sha256,
            external_b_sha256=a.external_b_sha256,
            external_a_sequence_floor=a.external_a_sequence_floor,
            external_b_sequence_floor=a.external_b_sequence_floor,
            expected_generation=a.expected_generation,
            expected_pair_pin=a.expected_pair_pin,
            expected_event_head=a.expected_event_head))
        status=0
    except (HighwaterConflict,cas.CheckpointCASConflict,
            ValueError,OSError,TypeError,KeyError,IndexError,
            sqlite3.DatabaseError):
        report['independent_floor_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
