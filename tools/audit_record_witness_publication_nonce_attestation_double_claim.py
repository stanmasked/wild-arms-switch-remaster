"""Stage 264N: offline conflicting / nonce-reused signed attestation claims.

Two full, exact-byte-pinned Stage 264M Ed25519 envelopes from ONE enrolled
operator are authenticated before reporting either (a) different statements
in one sequence+predecessor slot or (b) the same signed challenge reused in
separate sequence/predecessor slots. This is evidence about signed CLAIMS;
it does not prove that a referenced Stage 264L archive exists or was read,
nor enforce any off-host monotonic signing policy.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path

try:
    from . import audit_record_witness_publication_nonce_divergence_attestations as attest
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_nonce_divergence_attestations as attest
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-nonce-attestation-double-claim-evidence-v1'
REPORT_SCHEMA='wild-arms-ps1-nonce-attestation-double-claim-report-v1'
DOMAIN=b'wild-arms-ps1-nonce-attestation-double-claim-evidence-v1\x00'


class DoubleAttestationConflict(attest.AttestationConflict):
    """Expected authentic conflict between two attestation claims not proven."""


def _authenticate(raw,pin,*,scope,role,operator_id,audit_id,nonce,seq,previous,
                  archive_pin,genesis_a,genesis_b,head_a,head_b,public,public_pin):
    cas.digest(pin)
    if (type(raw) is not bytes or not 0<len(raw)<=attest.MAX_SIGNED
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
        raise DoubleAttestationConflict('signed attestation does not match independent pin')
    signed=_signed(raw,attest.SCHEMA,attest.DOMAIN,public_pin,public)
    if type(signed) is not dict or set(signed)!=attest.BODY_FIELDS:
        raise DoubleAttestationConflict('unexpected signed field set')
    if (signed.get('conflict_class') not in ('forked_hash_chains','strict_prefix_lag')
            or type(signed.get('common_verified_event_count')) is not int
            or signed['common_verified_event_count']<0):
        raise DoubleAttestationConflict('unsupported signed fork classification')
    # Validate and recreate every enrolled field, including mandatory NO
    # release / NO external custody flags. Do not treat signed claim as
    # proof that the actual archived nonce histories were observed.
    expected=attest._claim(role,operator_id,audit_id,nonce,seq,previous,
        scope,archive_pin,genesis_a,genesis_b,head_a,head_b,{
            'conflict_class':signed['conflict_class'],
            'common_verified_event_count':signed['common_verified_event_count'],
        })
    if signed!=expected:
        raise DoubleAttestationConflict('signed claim contradicts separately enrolled inputs')
    return signed


def verify(first,second,*,scope,role,operator_id,public,public_pin,
           first_envelope_pin,second_envelope_pin,
           first_audit_id,second_audit_id,
           first_nonce,second_nonce,
           first_sequence,second_sequence,
           first_previous_sha256,second_previous_sha256,
           first_archive_pin,second_archive_pin,
           genesis_a,genesis_b,
           first_head_a,first_head_b,second_head_a,second_head_b,
           expected_incident_sha256=None):
    """Read-only contradiction proof from exactly two enrolled signatures."""
    receipts._tag(scope)
    receipts._tag(operator_id)
    if role not in ('operator-a','operator-b'):
        raise DoubleAttestationConflict('wrong enrolled role')
    for item in (first_audit_id,second_audit_id):
        receipts._tag(item)
    for nonce in (first_nonce,second_nonce):
        receipts._nonce(nonce)
    for seq in (first_sequence,second_sequence):
        cas.number(seq,cas.MAX_SEQUENCE,'attestation sequence')
        if seq<1:
            raise DoubleAttestationConflict('nonpositive attestation sequence')
    for pin in (first_envelope_pin,second_envelope_pin,
                first_previous_sha256,second_previous_sha256,
                first_archive_pin,second_archive_pin,
                genesis_a,genesis_b,
                first_head_a,first_head_b,second_head_a,second_head_b):
        cas.digest(pin)
    receipts._enrolled_pem(public,public_pin)
    common=dict(scope=scope,role=role,operator_id=operator_id,
                genesis_a=genesis_a,genesis_b=genesis_b,public=public,
                public_pin=public_pin)
    a=_authenticate(first,first_envelope_pin,
        audit_id=first_audit_id,nonce=first_nonce,seq=first_sequence,
        previous=first_previous_sha256,archive_pin=first_archive_pin,
        head_a=first_head_a,head_b=first_head_b,**common)
    b=_authenticate(second,second_envelope_pin,
        audit_id=second_audit_id,nonce=second_nonce,seq=second_sequence,
        previous=second_previous_sha256,archive_pin=second_archive_pin,
        head_a=second_head_a,head_b=second_head_b,**common)
    if a==b:
        raise DoubleAttestationConflict('one signed claim is not two distinct issuances')
    same_slot=(first_sequence==second_sequence and
               first_previous_sha256==second_previous_sha256)
    same_nonce=first_nonce==second_nonce
    if not same_slot and not same_nonce:
        raise DoubleAttestationConflict('distinct claims are not a provable fork or nonce reuse')
    incident=('forked_same_predecessor_attestations' if same_slot
              else 'challenge_reused_across_attestation_slots')
    # Exclude signature bytes from canonical incident identity; two
    # differently encoded signatures on identical claims do NOT count.
    claims=sorted((a,b),key=lambda c:_canonical(c))
    digest_object={
        'schema':SCHEMA,'operator_role':role,'operator_id':operator_id,
        'checkpoint_scope':scope,'operator_public_pem_sha256':public_pin,
        'incident_type':incident,'claims':claims,
    }
    incident_sha=hashlib.sha256(DOMAIN+_canonical(digest_object)).hexdigest()
    if expected_incident_sha256 is not None and not hmac.compare_digest(
            cas.digest(expected_incident_sha256),incident_sha):
        raise DoubleAttestationConflict('incident does not match independent digest')
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_signed_attestation_claims_verified':True,
        'both_exact_signed_envelope_sha256_pins_verified':True,
        'same_enrolled_ed25519_public_key_role_scope_verified':True,
        'forked_same_predecessor_attestations_detected':same_slot,
        'challenge_reused_across_attestation_slots_detected':not same_slot,
        'incident_type':incident,
        'canonical_incident_sha256':incident_sha,
        'first_attestation_sha256':first_envelope_pin,
        'second_attestation_sha256':second_envelope_pin,
        'either_referenced_archive_was_inspected_proved':False,
        'signed_operator_honest_proved':False,
        'independent_challenge_freshness_proved':False,
        'externally_retained_incident_pin_proved':False,
        'offhost_monotonic_attestation_cas_proved':False,
        'automatic_ledger_merge_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first',type=Path)
    parser.add_argument('second',type=Path)
    parser.add_argument('--scope',required=True)
    parser.add_argument('--role',choices=('operator-a','operator-b'),required=True)
    parser.add_argument('--operator-id',required=True)
    parser.add_argument('--public',type=Path,required=True)
    parser.add_argument('--public-pin',required=True)
    parser.add_argument('--genesis-a',required=True)
    parser.add_argument('--genesis-b',required=True)
    for prefix in ('first','second'):
        parser.add_argument('--'+prefix+'-envelope-pin',required=True)
        parser.add_argument('--'+prefix+'-audit-id',required=True)
        parser.add_argument('--'+prefix+'-nonce',required=True)
        parser.add_argument('--'+prefix+'-sequence',type=int,required=True)
        parser.add_argument('--'+prefix+'-previous-sha256',required=True)
        parser.add_argument('--'+prefix+'-archive-pin',required=True)
        parser.add_argument('--'+prefix+'-head-a',required=True)
        parser.add_argument('--'+prefix+'-head-b',required=True)
    parser.add_argument('--expected-incident-sha256')
    args=parser.parse_args(argv)
    out={'schema':REPORT_SCHEMA,'automatic_ledger_merge_authorized':False,
         'automatic_cas_retry_authorized':False,
         'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False}
    try:
        one=_read_limited(_private_regular_file(args.first),attest.MAX_SIGNED)
        two=_read_limited(_private_regular_file(args.second),attest.MAX_SIGNED)
        kw=dict(scope=args.scope,role=args.role,operator_id=args.operator_id,
            public=args.public,public_pin=args.public_pin,
            genesis_a=args.genesis_a,genesis_b=args.genesis_b,
            expected_incident_sha256=args.expected_incident_sha256)
        for prefix in ('first','second'):
            for param,field in (
                ('envelope_pin','envelope_pin'),
                ('audit_id','audit_id'),('nonce','nonce'),
                ('sequence','sequence'),('previous_sha256','previous_sha256'),
                ('archive_pin','archive_pin'),
                ('head_a','head_a'),('head_b','head_b')):
                kw[prefix+'_'+param]=getattr(args,prefix+'_'+field)
        out.update(verify(one,two,**kw))
        status=0
    except (DoubleAttestationConflict,attest.AttestationConflict,
            receipts.ReceiptConflict,cas.CheckpointCASConflict,
            ValueError,KeyError,TypeError,IndexError,OSError):
        out['attestation_double_claim_conflict']=True
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
