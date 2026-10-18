"""Stage 264E: offline proof of two contradictory co-signed checkpoint successors.

Authenticate both complete Stage 264D signed bundles against independently
retained exact-byte SHA-256 pins and two separately enrolled operator keys.
Detect two different *checkpoint states at the same immediate generation*
endorsed from the exact same archived parent. Do not assume either state was
committed to the keeper. Never release a fence or mutate records.
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
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from . import audit_record_witness_publication_dual_operator_highwater as high
    from . import audit_record_witness_publication_highwater_lineage as lineage
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    import audit_record_witness_publication_checkpoint_cas as cas
    import audit_record_witness_publication_dual_operator_highwater as high
    import audit_record_witness_publication_highwater_lineage as lineage

SCHEMA = 'wild-arms-ps1-checkpoint-successor-equivocation-evidence-v1'
REPORT_SCHEMA = 'wild-arms-ps1-checkpoint-successor-equivocation-report-v1'
DOMAIN = b'wild-arms-ps1-checkpoint-successor-equivocation-evidence-v1\x00'
KEYS = frozenset(('old_a','old_b','new_a','new_b','endorsement_a','endorsement_b'))
HISTORY = ('generation','pair_sha256','event_head_sha256','event_count',
           'source_a_sequence','source_b_sequence')


class EquivocationConflict(cas.CheckpointCASConflict):
    """Two authentic, contradictory sibling transitions have not been proved."""


def _branch(bundle, pins, *, scope, ids, keys, previous_digest,
            parent_old_a_pin, parent_old_b_pin):
    if (type(bundle) is not dict or set(bundle) != KEYS
            or type(pins) is not dict or set(pins) != KEYS):
        raise EquivocationConflict('incomplete or unknown signed bundle field')
    for name in KEYS:
        cas.digest(pins[name])
        if (type(bundle[name]) is not bytes or not 0 < len(bundle[name]) <= (
                high.MAX_CERT if name.startswith(('old_','new_'))
                else lineage.MAX_ENDORSEMENT)):
            raise EquivocationConflict('invalid bounded signed bundle envelope')
        if not hmac.compare_digest(hashlib.sha256(bundle[name]).hexdigest(),
                                   pins[name]):
            raise EquivocationConflict('signed envelope bytes differ from external pin')
    if (pins['old_a'] != parent_old_a_pin
            or pins['old_b'] != parent_old_b_pin):
        raise EquivocationConflict('candidate does not share independently pinned parent')

    old, new = [], []
    for letter in ('a','b'):
        operator_id=ids[letter]
        public,pem_pin=keys[letter]
        before=high._certificate(bundle['old_'+letter],public,pem_pin,
                                pins['old_'+letter],0,operator_id,scope)
        after=high._certificate(bundle['new_'+letter],public,pem_pin,
                               pins['new_'+letter],
                               before['seal_sequence']+1,operator_id,scope)
        old.append(before)
        new.append(after)
    if (any(old[0][k] != old[1][k] for k in HISTORY)
            or any(new[0][k] != new[1][k] for k in HISTORY)):
        raise EquivocationConflict('paired operator certificates disagree')
    if (old[0]['generation'] >= cas.MAX_COUNT
            or new[0]['generation'] != old[0]['generation']+1
            or new[0]['event_count'] <= old[0]['event_count']
            or new[0]['source_a_sequence'] <= old[0]['source_a_sequence']
            or new[0]['source_b_sequence'] <= old[0]['source_b_sequence']
            or new[0]['pair_sha256'] == old[0]['pair_sha256']
            or new[0]['event_head_sha256'] == old[0]['event_head_sha256']):
        raise EquivocationConflict('candidate not an immediate strict successor')

    expected_body = {
        'schema':lineage.SCHEMA,'checkpoint_scope':scope,
        'previous_transition_bundle_sha256':previous_digest,
        'old_operator_a_certificate_sha256':pins['old_a'],
        'old_operator_b_certificate_sha256':pins['old_b'],
        'new_operator_a_certificate_sha256':pins['new_a'],
        'new_operator_b_certificate_sha256':pins['new_b'],
        'old_generation':old[0]['generation'],
        'old_pair_sha256':old[0]['pair_sha256'],
        'old_event_head_sha256':old[0]['event_head_sha256'],
        'new_generation':new[0]['generation'],
        'new_pair_sha256':new[0]['pair_sha256'],
        'new_event_head_sha256':new[0]['event_head_sha256'],
        'witness_fence_retirement_authorized':False,
    }
    for letter in ('a','b'):
        public,pem_pin=keys[letter]
        body=_signed(bundle['endorsement_'+letter],lineage.SCHEMA,
                     lineage.DOMAIN,pem_pin,public)
        if (type(body) is not dict or set(body) != lineage.BODY_FIELDS
                or body != dict(expected_body,operator_id=ids[letter])):
            raise EquivocationConflict('transition signature does not bind sibling claim')
    digest=lineage.proposed_bundle_digest(
        bundle['endorsement_a'],bundle['endorsement_b'],scope=scope,
        previous_transition_bundle_sha256=previous_digest,
        source_old_a=pins['old_a'],source_old_b=pins['old_b'],
        source_new_a=pins['new_a'],source_new_b=pins['new_b'])
    return {'old':old[0],'new':new[0],'bundle_sha256':digest,
            'new_a_sha256':pins['new_a'],'new_b_sha256':pins['new_b']}


def verify(branch_a, branch_b, pins_a, pins_b, *,
           scope, operator_a_id, operator_b_id,
           operator_a_public, operator_a_pin,
           operator_b_public, operator_b_pin,
           parent_old_a_pin, parent_old_b_pin,
           previous_transition_bundle_sha256,
           expected_parent_generation, expected_parent_pair_pin,
           expected_parent_event_head,
           externally_pinned_evidence_sha256=None):
    """Return canonical evidence hash only when *both* valid siblings disagree."""
    if (type(scope) is not str or not high.TAG.fullmatch(scope)
            or any(type(x) is not str or not high.TAG.fullmatch(x)
                   for x in (operator_a_id,operator_b_id))
            or operator_a_id == operator_b_id):
        raise EquivocationConflict('invalid independently enrolled operator identities')
    for pin in (parent_old_a_pin,parent_old_b_pin,
                previous_transition_bundle_sha256,
                expected_parent_pair_pin,expected_parent_event_head):
        cas.digest(pin)
    cas.number(expected_parent_generation,cas.MAX_COUNT,'expected parent generation')
    if (high._key_identity(operator_a_public,operator_a_pin) ==
            high._key_identity(operator_b_public,operator_b_pin)):
        raise EquivocationConflict('two operators must have distinct DER key identities')
    keys={'a':(operator_a_public,operator_a_pin),
          'b':(operator_b_public,operator_b_pin)}
    ids={'a':operator_a_id,'b':operator_b_id}
    kwargs=dict(scope=scope,ids=ids,keys=keys,
                previous_digest=previous_transition_bundle_sha256,
                parent_old_a_pin=parent_old_a_pin,
                parent_old_b_pin=parent_old_b_pin)
    first=_branch(branch_a,pins_a,**kwargs)
    second=_branch(branch_b,pins_b,**kwargs)
    if (branch_a['old_a'] != branch_b['old_a']
            or branch_a['old_b'] != branch_b['old_b']):
        raise EquivocationConflict('fork cannot have different parent certificates')
    anchor=first['old']
    if (any(first['old'][k] != second['old'][k] for k in HISTORY)
            or anchor['generation'] != expected_parent_generation
            or anchor['pair_sha256'] != expected_parent_pair_pin
            or anchor['event_head_sha256'] != expected_parent_event_head):
        raise EquivocationConflict('fork does not descend from independently pinned state')
    a,b=first['new'],second['new']
    if (a['generation'] != b['generation']
            or a['pair_sha256'] == b['pair_sha256']
            or a['event_head_sha256'] == b['event_head_sha256']
            or first['bundle_sha256'] == second['bundle_sha256']):
        raise EquivocationConflict('no contradictory successor states at same generation')
    sorted_claims=sorted((first,second),key=lambda c:c['bundle_sha256'])
    evidence={
        'schema':SCHEMA,
        'checkpoint_scope':scope,
        'previous_transition_bundle_sha256':previous_transition_bundle_sha256,
        'parent_generation':anchor['generation'],
        'parent_pair_sha256':anchor['pair_sha256'],
        'parent_event_head_sha256':anchor['event_head_sha256'],
        'parent_operator_a_certificate_sha256':parent_old_a_pin,
        'parent_operator_b_certificate_sha256':parent_old_b_pin,
        'successors':[{
            'bundle_sha256':x['bundle_sha256'],
            'generation':x['new']['generation'],
            'pair_sha256':x['new']['pair_sha256'],
            'event_head_sha256':x['new']['event_head_sha256'],
            'operator_a_certificate_sha256':x['new_a_sha256'],
            'operator_b_certificate_sha256':x['new_b_sha256'],
        } for x in sorted_claims],
    }
    evidence_pin=hashlib.sha256(DOMAIN+_canonical(evidence)).hexdigest()
    if externally_pinned_evidence_sha256 is not None:
        if not hmac.compare_digest(cas.digest(externally_pinned_evidence_sha256),
                                   evidence_pin):
            raise EquivocationConflict('separately enrolled evidence pin changed')
    return {
        'schema':REPORT_SCHEMA,
        'two_valid_operator_countersigned_sibling_claims_verified':True,
        'same_exact_pinned_parent_and_previous_bundle_verified':True,
        'contradictory_successor_checkpoint_states_proved':True,
        'successors_are_same_immediate_generation':True,
        'canonical_evidence_sha256':evidence_pin,
        'parent_generation':anchor['generation'],
        'conflicting_successor_generation':a['generation'],
        'conflicting_bundle_sha256s':[c['bundle_sha256'] for c in sorted_claims],
        'conflicting_pair_sha256s':[c['new']['pair_sha256'] for c in sorted_claims],
        'conflicting_event_head_sha256s':[c['new']['event_head_sha256']
                                          for c in sorted_claims],
        'real_independent_operator_custody_proved':False,
        'either_successor_was_committed_to_keeper_proved':False,
        'externally_archived_evidence_proved':False,
        'global_latest_head_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scope',required=True)
    for letter in ('a','b'):
        p.add_argument('--operator-'+letter+'-id',required=True)
        p.add_argument('--operator-'+letter+'-public',type=Path,required=True)
        p.add_argument('--operator-'+letter+'-pin',required=True)
    p.add_argument('--parent-old-a-sha256',required=True)
    p.add_argument('--parent-old-b-sha256',required=True)
    p.add_argument('--previous-transition-bundle-sha256',required=True)
    p.add_argument('--expected-parent-generation',type=int,required=True)
    p.add_argument('--expected-parent-pair-pin',required=True)
    p.add_argument('--expected-parent-event-head',required=True)
    p.add_argument('--externally-pinned-evidence-sha256')
    for branch in ('left','right'):
        for name in sorted(KEYS):
            p.add_argument('--'+branch+'-'+name.replace('_','-'),
                           type=Path,required=True)
            p.add_argument('--'+branch+'-'+name.replace('_','-')+'-sha256',
                           required=True)
    a=p.parse_args(argv)
    output={
        'schema':REPORT_SCHEMA,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
    }
    try:
        bundle={}
        hashes={}
        for direction in ('left','right'):
            bundle[direction]={}
            hashes[direction]={}
            for name in KEYS:
                key=direction+'_'+name
                bundle[direction][name]=_read_limited(
                    _private_regular_file(getattr(a,key)),
                    high.MAX_CERT if name.startswith(('old_','new_'))
                    else lineage.MAX_ENDORSEMENT)
                hashes[direction][name]=getattr(a,key+'_sha256')
        output.update(verify(bundle['left'],bundle['right'],
            hashes['left'],hashes['right'],
            scope=a.scope,operator_a_id=a.operator_a_id,
            operator_b_id=a.operator_b_id,
            operator_a_public=a.operator_a_public,
            operator_a_pin=a.operator_a_pin,
            operator_b_public=a.operator_b_public,
            operator_b_pin=a.operator_b_pin,
            parent_old_a_pin=a.parent_old_a_sha256,
            parent_old_b_pin=a.parent_old_b_sha256,
            previous_transition_bundle_sha256=a.previous_transition_bundle_sha256,
            expected_parent_generation=a.expected_parent_generation,
            expected_parent_pair_pin=a.expected_parent_pair_pin,
            expected_parent_event_head=a.expected_parent_event_head,
            externally_pinned_evidence_sha256=a.externally_pinned_evidence_sha256))
        status=0
    except (EquivocationConflict,cas.CheckpointCASConflict,
            ValueError,OSError,TypeError,KeyError,IndexError):
        output['equivocation_evidence_conflict']=True
        status=1
    print(json.dumps(output,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
