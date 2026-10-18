"""Stage 264R: detect one mirror-audit signer's double claims or nonce reuse.

Two exact SHA-256-pinned, complete Stage 264Q Ed25519 envelopes are
authenticated under ONE externally enrolled public key. Either two distinct
claims share the same sequence and predecessor, or a nonce was reused across
different sequence/predecessor slots. This is archival evidence of authentic
SIGNED CLAIMS ONLY; it cannot establish that the underlying mirrored
registries, private manifest or two operators actually existed.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path

try:
    from . import audit_record_witness_publication_signed_mirror_acknowledgments as signed
    from . import audit_record_witness_publication_attestation_registry_binding as bound
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_signed_mirror_acknowledgments as signed
    import audit_record_witness_publication_attestation_registry_binding as bound
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-signed-mirror-double-claim-evidence-v1'
REPORT_SCHEMA='wild-arms-ps1-signed-mirror-double-claim-report-v1'
DOMAIN=b'wild-arms-ps1-signed-mirror-double-claim-evidence-v1\x00'


class MirrorDoubleClaimConflict(signed.SignedMirrorConflict):
    """Supplied bytes do not establish two authentic contradictory claims."""


def _attested_claim(raw,pin,*,role,operator_id,scope,audit_id,
                    nonce,sequence,previous,public,public_pin,
                    genesis_a,genesis_b):
    cas.digest(pin)
    if (type(raw) is not bytes or not 0<len(raw)<=signed.MAX_SIGNED
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
        raise MirrorDoubleClaimConflict('signed claim not independently pinned')
    claim=_signed(raw,signed.SCHEMA,signed.DOMAIN,public_pin,public)
    if type(claim) is not dict or set(claim)!=signed.BODY_FIELDS:
        raise MirrorDoubleClaimConflict('signed mirror claim fields unexpected')
    pending=claim['pending_operator_roles']
    if (type(pending) is not list or len(set(pending))!=len(pending)
            or any(type(x) is not str or x not in ('operator-a','operator-b')
                   for x in pending)
            or type(claim['verified_event_count']) is not int
            or type(claim['verified_signed_completion_count']) is not int
            or claim['verified_event_count']<claim['verified_signed_completion_count']
            or claim['verified_signed_completion_count']<1):
        raise MirrorDoubleClaimConflict('invalid audited result asserted by signature')
    # Reconstruct the *complete* Stage Q canonical body, including
    # no-custody/no-release claims. The audit summary is a signed assertion;
    # it is NOT independent evidence that Stage P was actually run.
    asserted=dict(schema=bound.SCHEMA,
        every_completed_event_binds_pinned_ed25519_attestation=True,
        all_ed25519_signatures_bind_canonical_pre_sign_body=True,
        verified_signed_completion_count=claim['verified_signed_completion_count'],
        verified_event_count=claim['verified_event_count'],
        pending_operator_roles=pending)
    expected=signed.expected_body(asserted,scope=scope,audit_id=audit_id,
        operator_role=role,operator_id=operator_id,challenge=nonce,
        sequence=sequence,previous_sha256=previous,
        genesis_a=genesis_a,genesis_b=genesis_b,
        head_a=claim['primary_head_sha256'],head_b=claim['secondary_head_sha256'],
        manifest_sha256=claim['exact_signed_completion_manifest_sha256'])
    if claim!=expected:
        raise MirrorDoubleClaimConflict('signed mirror claim contradicts enrolled context')
    return claim


def verify(first,second,*,scope,role,operator_id,public,public_pin,
           genesis_a,genesis_b,
           first_envelope_pin,second_envelope_pin,
           first_audit_id,second_audit_id,
           first_nonce,second_nonce,
           first_sequence,second_sequence,
           first_previous_sha256,second_previous_sha256,
           expected_incident_sha256=None):
    receipts._tag(scope)
    receipts._tag(operator_id)
    if role not in ('operator-a','operator-b'):
        raise MirrorDoubleClaimConflict('invalid enrolled operator role')
    for audit in (first_audit_id,second_audit_id):
        receipts._tag(audit)
    for nonce in (first_nonce,second_nonce):
        receipts._nonce(nonce)
    for seq in (first_sequence,second_sequence):
        cas.number(seq,cas.MAX_SEQUENCE,'acknowledgment sequence')
        if seq<1:
            raise MirrorDoubleClaimConflict('invalid acknowledgment sequence')
    for pin in (first_envelope_pin,second_envelope_pin,
                first_previous_sha256,second_previous_sha256,
                genesis_a,genesis_b,public_pin):
        cas.digest(pin)
    receipts._enrolled_pem(public,public_pin)
    common=dict(scope=scope,role=role,operator_id=operator_id,
                public=public,public_pin=public_pin,
                genesis_a=genesis_a,genesis_b=genesis_b)
    a=_attested_claim(first,first_envelope_pin,
        audit_id=first_audit_id,nonce=first_nonce,
        sequence=first_sequence,previous=first_previous_sha256,**common)
    b=_attested_claim(second,second_envelope_pin,
        audit_id=second_audit_id,nonce=second_nonce,
        sequence=second_sequence,previous=second_previous_sha256,**common)
    if a==b:
        raise MirrorDoubleClaimConflict('replayed identical claim is not a second issuance')
    same_slot=(first_sequence==second_sequence and
               first_previous_sha256==second_previous_sha256)
    reused_nonce=first_nonce==second_nonce
    if not (same_slot or reused_nonce):
        raise MirrorDoubleClaimConflict('no same-slot fork or reused challenge')
    incident=('forked_same_predecessor_mirror_acknowledgments' if same_slot
              else 'challenge_reused_across_mirror_acknowledgment_slots')
    # Signature bytes/order do not define the incident. Identical
    # authenticated bodies never count as separate conflicting claims.
    claims=sorted((a,b),key=_canonical)
    report_body=dict(schema=SCHEMA,operator_role=role,operator_id=operator_id,
        checkpoint_scope=scope,operator_public_pem_sha256=public_pin,
        incident_type=incident,claims=claims)
    incident_sha=hashlib.sha256(DOMAIN+_canonical(report_body)).hexdigest()
    if (expected_incident_sha256 is not None and not hmac.compare_digest(
            cas.digest(expected_incident_sha256),incident_sha)):
        raise MirrorDoubleClaimConflict('independently expected incident digest mismatch')
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_ed25519_mirror_acknowledgment_claims_verified':True,
        'both_exact_signed_envelope_pins_matched':True,
        'same_enrolled_ed25519_operator_scope_verified':True,
        'forked_same_predecessor_mirror_acknowledgments_detected':same_slot,
        'challenge_reused_across_mirror_acknowledgment_slots_detected':
            (not same_slot),
        'incident_type':incident,
        'canonical_incident_sha256':incident_sha,
        'first_signed_envelope_sha256':first_envelope_pin,
        'second_signed_envelope_sha256':second_envelope_pin,
        'either_underlying_sqlite_registry_audited_proved':False,
        'any_attested_manifest_envelopes_were_revalidated_proved':False,
        'actual_independent_physical_operator_custody_proved':False,
        'independent_challenge_freshness_proved':False,
        'externally_retained_incident_digest_proved':False,
        'global_attestation_nonce_cas_proved':False,
        'automatic_register_sync_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('first',type=Path)
    p.add_argument('second',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--role',choices=('operator-a','operator-b'),required=True)
    p.add_argument('--operator-id',required=True)
    p.add_argument('--public',type=Path,required=True)
    p.add_argument('--public-pin',required=True)
    p.add_argument('--genesis-a',required=True)
    p.add_argument('--genesis-b',required=True)
    for prefix in ('first','second'):
        p.add_argument('--'+prefix+'-envelope-pin',required=True)
        p.add_argument('--'+prefix+'-audit-id',required=True)
        p.add_argument('--'+prefix+'-nonce',required=True)
        p.add_argument('--'+prefix+'-sequence',type=int,required=True)
        p.add_argument('--'+prefix+'-previous-sha256',required=True)
    p.add_argument('--expected-incident-sha256')
    args=p.parse_args(argv)
    out={'schema':REPORT_SCHEMA,'automatic_register_sync_authorized':False,
         'automatic_cas_retry_authorized':False,
         'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False}
    try:
        first=_read_limited(_private_regular_file(args.first),signed.MAX_SIGNED)
        second=_read_limited(_private_regular_file(args.second),signed.MAX_SIGNED)
        out.update(verify(first,second,scope=args.scope,role=args.role,
            operator_id=args.operator_id,public=args.public,
            public_pin=args.public_pin,genesis_a=args.genesis_a,
            genesis_b=args.genesis_b,
            first_envelope_pin=args.first_envelope_pin,
            second_envelope_pin=args.second_envelope_pin,
            first_audit_id=args.first_audit_id,
            second_audit_id=args.second_audit_id,
            first_nonce=args.first_nonce,second_nonce=args.second_nonce,
            first_sequence=args.first_sequence,
            second_sequence=args.second_sequence,
            first_previous_sha256=args.first_previous_sha256,
            second_previous_sha256=args.second_previous_sha256,
            expected_incident_sha256=args.expected_incident_sha256))
        status=0
    except (MirrorDoubleClaimConflict,signed.SignedMirrorConflict,
            receipts.ReceiptConflict,cas.CheckpointCASConflict,
            ValueError,KeyError,TypeError,IndexError,OSError):
        out['signed_mirror_double_claim_conflict']=True
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
