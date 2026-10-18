"""Stage 264D: two Ed25519 attestations bind consecutive operator highwaters.

Read only. Verifies four externally pinned highwater certificates (old and
successor, from two separate operators), two freshly signed matching
transition endorsements, and a complete keeper history under independently
supplied current head pins. This does NOT prove an external CAS or uniqueness
of concurrently signed successors without an independently retained new pin.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import _signed
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from . import audit_record_witness_publication_dual_operator_highwater as high
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    import audit_record_witness_publication_checkpoint_cas as cas
    import audit_record_witness_publication_dual_operator_highwater as high

SCHEMA = 'wild-arms-ps1-paired-highwater-transition-endorsement-v1'
REPORT_SCHEMA = 'wild-arms-ps1-paired-highwater-transition-report-v1'
DOMAIN = b'wild-arms-ps1-paired-highwater-transition-endorsement-v1\x00'
BUNDLE_DOMAIN = b'wild-arms-ps1-paired-highwater-transition-bundle-v1\x00'
MAX_ENDORSEMENT = 2048
BODY_FIELDS = {
    'schema','operator_id','checkpoint_scope',
    'previous_transition_bundle_sha256',
    'old_operator_a_certificate_sha256','old_operator_b_certificate_sha256',
    'new_operator_a_certificate_sha256','new_operator_b_certificate_sha256',
    'old_generation','old_pair_sha256','old_event_head_sha256',
    'new_generation','new_pair_sha256','new_event_head_sha256',
    'witness_fence_retirement_authorized',
}
COMPARED_FIELDS = BODY_FIELDS - {'operator_id'}


class LineageConflict(cas.CheckpointCASConflict):
    """A trust pin, signed endorsement, or monotonically ordered link differs."""


def _pinned_cert(raw,pin,public,public_pin,operator_id,scope,min_seq):
    return high._certificate(raw,public,public_pin,pin,min_seq,
                             operator_id,scope)


def proposed_bundle_digest(signed_a,signed_b, *,
                           previous_transition_bundle_sha256,
                           source_old_a,source_old_b,source_new_a,source_new_b,
                           scope):
    if type(scope) is not str or not high.TAG.fullmatch(scope):
        raise LineageConflict('invalid enrolled scope')
    for value in (previous_transition_bundle_sha256,source_old_a,source_old_b,
                  source_new_a,source_new_b):
        cas.digest(value)
    for raw in (signed_a,signed_b):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_ENDORSEMENT:
            raise LineageConflict('invalid bounded transition signatures')
    return hashlib.sha256(BUNDLE_DOMAIN + _canonical({
        'schema':SCHEMA,'scope':scope,
        'previous_transition_bundle_sha256':previous_transition_bundle_sha256,
        'old_certificate_a_sha256':source_old_a,
        'old_certificate_b_sha256':source_old_b,
        'new_certificate_a_sha256':source_new_a,
        'new_certificate_b_sha256':source_new_b,
        'endorsement_a_envelope_sha256':hashlib.sha256(signed_a).hexdigest(),
        'endorsement_b_envelope_sha256':hashlib.sha256(signed_b).hexdigest(),
    })).hexdigest()


def verify(path, old_a,old_b,new_a,new_b,signed_a,signed_b, *,
           scope, operator_a_id,operator_b_id,
           operator_a_public,operator_a_pin,
           operator_b_public,operator_b_pin,
           externally_pinned,
           previous_transition_bundle_sha256,
           expected_generation,expected_pair_pin,expected_event_head,
           expected_successor_bundle_sha256=None):
    """Accept only two fully signed endorsements of the SAME strict link.

    externally_pinned contains old_a, old_b, new_a, new_b, endorsement_a,
    endorsement_b: the SHA-256 values independently kept off the local host.
    """
    if (type(externally_pinned) is not dict or set(externally_pinned) !=
            {'old_a','old_b','new_a','new_b','endorsement_a','endorsement_b'}
            or type(scope) is not str or not high.TAG.fullmatch(scope)
            or type(operator_a_id) is not str or not high.TAG.fullmatch(operator_a_id)
            or type(operator_b_id) is not str or not high.TAG.fullmatch(operator_b_id)
            or operator_a_id == operator_b_id):
        raise LineageConflict('invalid independently enrolled transition context')
    for sha in externally_pinned.values():
        cas.digest(sha)
    cas.digest(previous_transition_bundle_sha256)
    if (high._key_identity(operator_a_public,operator_a_pin) ==
            high._key_identity(operator_b_public,operator_b_pin)):
        raise LineageConflict('same operator DER key cannot endorse both roles')
    old=[]
    new=[]
    for idx,(operator_id,public,pin) in enumerate((
            (operator_a_id,operator_a_public,operator_a_pin),
            (operator_b_id,operator_b_public,operator_b_pin))):
        letter=('a','b')[idx]
        old_raw=(old_a,old_b)[idx]
        new_raw=(new_a,new_b)[idx]
        # Independent exact-byte pins, signature and body schema enforced
        # by the Stage 264C certificate parser. Do not accept a bare SHA.
        prior=_pinned_cert(old_raw,externally_pinned['old_'+letter],
                          public,pin,operator_id,scope,0)
        successor=_pinned_cert(new_raw,externally_pinned['new_'+letter],
                              public,pin,operator_id,scope,prior['seal_sequence']+1)
        old.append(prior)
        new.append(successor)
    history_fields=('generation','pair_sha256','event_head_sha256','event_count',
                    'source_a_sequence','source_b_sequence')
    if (any(old[0][k] != old[1][k] for k in history_fields)
            or any(new[0][k] != new[1][k] for k in history_fields)):
        raise LineageConflict('old or successor operator highwater pair disagrees')
    if (new[0]['generation'] <= old[0]['generation']
            or new[0]['event_count'] <= old[0]['event_count']
            or new[0]['source_a_sequence'] <= old[0]['source_a_sequence']
            or new[0]['source_b_sequence'] <= old[0]['source_b_sequence']
            or new[0]['pair_sha256'] == old[0]['pair_sha256']
            or new[0]['event_head_sha256'] == old[0]['event_head_sha256']):
        raise LineageConflict('new signed operator highwater did not advance')
    cas.number(expected_generation,cas.MAX_COUNT,'expected keeper generation')
    cas.digest(expected_pair_pin)
    cas.digest(expected_event_head)
    if (expected_generation != new[0]['generation']
            or expected_pair_pin != new[0]['pair_sha256']
            or expected_event_head != new[0]['event_head_sha256']):
        raise LineageConflict('successor must be exact enrolled keeper head')
    expected_body={
        'schema':SCHEMA,
        'checkpoint_scope':scope,
        'previous_transition_bundle_sha256':previous_transition_bundle_sha256,
        'old_operator_a_certificate_sha256':externally_pinned['old_a'],
        'old_operator_b_certificate_sha256':externally_pinned['old_b'],
        'new_operator_a_certificate_sha256':externally_pinned['new_a'],
        'new_operator_b_certificate_sha256':externally_pinned['new_b'],
        'old_generation':old[0]['generation'],
        'old_pair_sha256':old[0]['pair_sha256'],
        'old_event_head_sha256':old[0]['event_head_sha256'],
        'new_generation':new[0]['generation'],
        'new_pair_sha256':new[0]['pair_sha256'],
        'new_event_head_sha256':new[0]['event_head_sha256'],
        'witness_fence_retirement_authorized':False,
    }
    for idx,(signed,operator_id,public,pin) in enumerate((
            (signed_a,operator_a_id,operator_a_public,operator_a_pin),
            (signed_b,operator_b_id,operator_b_public,operator_b_pin))):
        letter=('a','b')[idx]
        if (type(signed) is not bytes or not 0 < len(signed) <= MAX_ENDORSEMENT
                or not hmac.compare_digest(hashlib.sha256(signed).hexdigest(),
                                           externally_pinned['endorsement_'+letter])):
            raise LineageConflict('exact endorsement envelope not externally pinned')
        actual=_signed(signed,SCHEMA,DOMAIN,pin,public)
        if (type(actual) is not dict or set(actual) != BODY_FIELDS
                or actual != dict(expected_body,operator_id=operator_id)):
            raise LineageConflict('operator endorsement does not bind both certificates')
    bundle=proposed_bundle_digest(
        signed_a,signed_b,scope=scope,
        previous_transition_bundle_sha256=previous_transition_bundle_sha256,
        source_old_a=externally_pinned['old_a'],
        source_old_b=externally_pinned['old_b'],
        source_new_a=externally_pinned['new_a'],
        source_new_b=externally_pinned['new_b'])
    if expected_successor_bundle_sha256 is not None:
        if not hmac.compare_digest(cas.digest(expected_successor_bundle_sha256),
                                   bundle):
            raise LineageConflict('externally pinned successor transition differs')
    # Stage 264C fully reaudits keeper twice per call and proves the old anchor
    # is in the exact same history ending at the independently trusted new head.
    for cert_a,cert_b,tag in ((old_a,old_b,'old'),(new_a,new_b,'new')):
        high.verify(path,cert_a,cert_b,
            scope=scope,operator_a_id=operator_a_id,operator_b_id=operator_b_id,
            operator_a_public=operator_a_public,operator_a_pin=operator_a_pin,
            operator_b_public=operator_b_public,operator_b_pin=operator_b_pin,
            external_a_sha256=externally_pinned[tag+'_a'],
            external_b_sha256=externally_pinned[tag+'_b'],
            external_a_sequence_floor=0,external_b_sequence_floor=0,
            expected_generation=expected_generation,
            expected_pair_pin=expected_pair_pin,
            expected_event_head=expected_event_head)
    return {
        'schema': REPORT_SCHEMA,
        'two_signed_paired_highwaters_strictly_advanced':True,
        'two_independently_pinned_transition_endorsements_verified':True,
        'both_operator_endorsements_bind_same_old_and_new_certificates':True,
        'old_and_new_history_anchors_in_fully_audited_keeper':True,
        'new_checkpoint_matches_independently_supplied_current_head':True,
        'previous_transition_bundle_sha256':previous_transition_bundle_sha256,
        'proposed_successor_transition_bundle_sha256':bundle,
        'old_generation':old[0]['generation'],
        'new_generation':new[0]['generation'],
        'externally_persisted_successor_bundle_proved':False,
        'unique_successor_or_fork_absence_proved':False,
        'real_external_operator_independence_proved':False,
        'globally_latest_publication_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('database',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--operator-a-id',required=True)
    p.add_argument('--operator-b-id',required=True)
    for name in ('a','b'):
        p.add_argument('--operator-'+name+'-public',type=Path,required=True)
        p.add_argument('--operator-'+name+'-pin',required=True)
        for moment in ('old','new'):
            p.add_argument('--'+moment+'-'+name+'-certificate',type=Path,required=True)
            p.add_argument('--'+moment+'-'+name+'-sha256',required=True)
        p.add_argument('--endorsement-'+name,type=Path,required=True)
        p.add_argument('--endorsement-'+name+'-sha256',required=True)
    p.add_argument('--previous-transition-bundle-sha256',required=True)
    p.add_argument('--expected-generation',type=int,required=True)
    p.add_argument('--expected-pair-pin',required=True)
    p.add_argument('--expected-event-head',required=True)
    p.add_argument('--expected-successor-bundle-sha256')
    a=p.parse_args(argv)
    report={'schema':REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False,
            'automatic_cas_retry_authorized':False}
    try:
        raw={}
        pinned={}
        for moment in ('old','new'):
            for letter in ('a','b'):
                label=moment+'_'+letter
                path=getattr(a,moment+'_'+letter+'_certificate')
                raw[label]=_read_limited(_private_regular_file(path),high.MAX_CERT)
                pinned[label]=getattr(a,moment+'_'+letter+'_sha256')
        for letter in ('a','b'):
            raw['endorsement_'+letter]=_read_limited(
                _private_regular_file(getattr(a,'endorsement_'+letter)),MAX_ENDORSEMENT)
            pinned['endorsement_'+letter]=getattr(a,'endorsement_'+letter+'_sha256')
        report.update(verify(a.database,raw['old_a'],raw['old_b'],
            raw['new_a'],raw['new_b'],raw['endorsement_a'],raw['endorsement_b'],
            scope=a.scope,operator_a_id=a.operator_a_id,
            operator_b_id=a.operator_b_id,
            operator_a_public=a.operator_a_public,
            operator_a_pin=a.operator_a_pin,
            operator_b_public=a.operator_b_public,
            operator_b_pin=a.operator_b_pin,
            externally_pinned=pinned,
            previous_transition_bundle_sha256=a.previous_transition_bundle_sha256,
            expected_generation=a.expected_generation,
            expected_pair_pin=a.expected_pair_pin,
            expected_event_head=a.expected_event_head,
            expected_successor_bundle_sha256=a.expected_successor_bundle_sha256))
        status=0
    except (LineageConflict,cas.CheckpointCASConflict,ValueError,OSError,
            TypeError,KeyError,IndexError,sqlite3.DatabaseError):
        report['highwater_transition_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
