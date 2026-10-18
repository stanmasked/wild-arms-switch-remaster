"""Stage 264I: offline evidence of duplicate challenge / co-signed receipt claims.

Two separately SHA-256-pinned, valid Ed25519 receipts by ONE enrolled
operator are audited as distinct claims under ONE independently supplied nonce.
The checker detects (a) conflicting archive/storage claims at the SAME audit,
sequence and predecessor, or (b) reuse of the nonce in different authenticated
audit/sequence/predecessor contexts. Merely differing envelope bytes is NOT
evidence of two different claims. No filesystem archive, external nonce
allocator or globally monotonic receipt register is proved or modified.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path

try:
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-archive-receipt-challenge-conflict-evidence-v1'
REPORT_SCHEMA='wild-arms-ps1-archive-receipt-challenge-conflict-report-v1'
DOMAIN=b'wild-arms-ps1-archive-receipt-challenge-conflict-evidence-v1\x00'
CONFLICT_FIELDS=('storage_id','archive_sha256','canonical_evidence_sha256')
UNIT_FIELDS=('audit_id','receipt_sequence','previous_receipt_sha256')


class ChallengeReuseConflict(receipts.ReceiptConflict):
    """The pinned signed evidence is not a verifiable challenge reuse."""


def _claim(raw,pin,*,role,operator_id,scope,audit_id,nonce,sequence,
           previous_sha256,public,public_pin):
    cas.digest(pin)
    if (type(raw) is not bytes or not 0 < len(raw) <= receipts.MAX_RECEIPT
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
        raise ChallengeReuseConflict('signed operator receipt not independently pinned')
    body=_signed(raw,receipts.SCHEMA,receipts.DOMAIN,public_pin,public)
    if type(body) is not dict or set(body) != receipts.BODY_FIELDS:
        raise ChallengeReuseConflict('signed receipt claims incomplete or unknown')
    if (body['schema'] != receipts.SCHEMA
            or body['operator_role'] != role
            or body['operator_id'] != operator_id
            or body['checkpoint_scope'] != scope
            or body['audit_id'] != audit_id
            or body['challenge_nonce'] != nonce
            or body['receipt_sequence'] != sequence
            or body['previous_receipt_sha256'] != previous_sha256):
        raise ChallengeReuseConflict('signed receipt differs from independently pinned context')
    # Canonical re-derivation rejects bool/integer confusion, unknown
    # identifiers and flags pretending custody or authorizing fence release.
    expected=receipts._body(
        role,operator_id,body['storage_id'],scope,audit_id,nonce,sequence,
        previous_sha256,body['archive_sha256'],body['canonical_evidence_sha256'])
    if expected != body:
        raise ChallengeReuseConflict('signed receipt contains unauthorized assertions')
    return body


def verify(first,second, *,
           scope,role,operator_id,nonce,operator_public,operator_public_pin,
           first_envelope_pin,second_envelope_pin,
           first_audit_id,second_audit_id,
           first_sequence,second_sequence,
           first_previous_sha256,second_previous_sha256,
           expected_incident_sha256=None):
    """Identify only distinct authentic claims that repeat one enrolled nonce."""
    for field in (scope,operator_id,first_audit_id,second_audit_id):
        receipts._tag(field)
    if role not in ('operator-a','operator-b'):
        raise ChallengeReuseConflict('invalid expected signer role')
    receipts._nonce(nonce)
    if (type(first_sequence) is not int or type(second_sequence) is not int
            or first_sequence < 1 or second_sequence < 1):
        raise ChallengeReuseConflict('invalid enrolled receipt sequences')
    for pin in (operator_public_pin,first_envelope_pin,second_envelope_pin,
                first_previous_sha256,second_previous_sha256):
        cas.digest(pin)
    # The pinned DER identity must match the exact enrolled PEM bytes.
    receipts._enrolled_pem(operator_public,operator_public_pin)
    a=_claim(first,first_envelope_pin,role=role,operator_id=operator_id,
             scope=scope,audit_id=first_audit_id,nonce=nonce,
             sequence=first_sequence,previous_sha256=first_previous_sha256,
             public=operator_public,public_pin=operator_public_pin)
    b=_claim(second,second_envelope_pin,role=role,operator_id=operator_id,
             scope=scope,audit_id=second_audit_id,nonce=nonce,
             sequence=second_sequence,previous_sha256=second_previous_sha256,
             public=operator_public,public_pin=operator_public_pin)
    if a == b:
        raise ChallengeReuseConflict('identical signed claim is not proof of a second issuance')
    same_unit=all(a[name] == b[name] for name in UNIT_FIELDS)
    different_copy=any(a[name] != b[name] for name in CONFLICT_FIELDS)
    if same_unit and not different_copy:
        raise ChallengeReuseConflict('no materially distinct receipt contents')
    incident='conflicting_same_predecessor_claims' if same_unit else 'cross_context_nonce_reuse'
    claims=sorted((a,b),key=lambda item:(
        item['audit_id'],item['receipt_sequence'],
        item['previous_receipt_sha256'],item['storage_id'],
        item['archive_sha256'],item['canonical_evidence_sha256']))
    evidence={
        'schema':SCHEMA,'operator_role':role,'operator_id':operator_id,
        'checkpoint_scope':scope,'challenge_nonce':nonce,
        'operator_public_pem_sha256':operator_public_pin,
        'incident_type':incident,
        'claims':[{
            'audit_id':c['audit_id'],
            'receipt_sequence':c['receipt_sequence'],
            'previous_receipt_sha256':c['previous_receipt_sha256'],
            'storage_id':c['storage_id'],
            'archive_sha256':c['archive_sha256'],
            'canonical_evidence_sha256':c['canonical_evidence_sha256'],
        } for c in claims],
    }
    evidence_hash=hashlib.sha256(DOMAIN+_canonical(evidence)).hexdigest()
    if expected_incident_sha256 is not None:
        if not hmac.compare_digest(cas.digest(expected_incident_sha256),
                                   evidence_hash):
            raise ChallengeReuseConflict('incident differs from independently retained digest')
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_signed_operator_receipt_claims_verified':True,
        'both_receipt_envelope_sha256_pins_matched':True,
        'same_operator_key_scope_role_and_challenge_verified':True,
        'conflicting_same_predecessor_claims_detected':same_unit,
        'reused_nonce_across_distinct_receipt_contexts_detected':not same_unit,
        'incident_type':incident,
        'canonical_incident_sha256':evidence_hash,
        'first_receipt_sha256':first_envelope_pin,
        'second_receipt_sha256':second_envelope_pin,
        'source_challenge_freshness_proved':False,
        'actual_archive_custody_proved':False,
        'either_claim_was_stored_or_committed_proved':False,
        'external_nonce_uniqueness_registry_proved':False,
        'honest_operator_behavior_proved':False,
        'independently_retained_incident_digest_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'automatic_cas_retry_authorized':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('first',type=Path)
    p.add_argument('second',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--role',choices=('operator-a','operator-b'),required=True)
    p.add_argument('--operator-id',required=True)
    p.add_argument('--nonce',required=True)
    p.add_argument('--operator-public',type=Path,required=True)
    p.add_argument('--operator-public-pin',required=True)
    p.add_argument('--first-envelope-pin',required=True)
    p.add_argument('--second-envelope-pin',required=True)
    for label in ('first','second'):
        p.add_argument('--'+label+'-audit-id',required=True)
        p.add_argument('--'+label+'-sequence',type=int,required=True)
        p.add_argument('--'+label+'-previous-sha256',required=True)
    p.add_argument('--expected-incident-sha256')
    a=p.parse_args(argv)
    outcome={'schema':REPORT_SCHEMA,'witness_fence_retirement_authorized':False,
             'witness_fence_retired':False,'automatic_cas_retry_authorized':False}
    try:
        first=_read_limited(_private_regular_file(a.first),receipts.MAX_RECEIPT)
        second=_read_limited(_private_regular_file(a.second),receipts.MAX_RECEIPT)
        outcome.update(verify(first,second,
            scope=a.scope,role=a.role,operator_id=a.operator_id,
            nonce=a.nonce,operator_public=a.operator_public,
            operator_public_pin=a.operator_public_pin,
            first_envelope_pin=a.first_envelope_pin,
            second_envelope_pin=a.second_envelope_pin,
            first_audit_id=a.first_audit_id,
            second_audit_id=a.second_audit_id,
            first_sequence=a.first_sequence,
            second_sequence=a.second_sequence,
            first_previous_sha256=a.first_previous_sha256,
            second_previous_sha256=a.second_previous_sha256,
            expected_incident_sha256=a.expected_incident_sha256))
        status=0
    except (ChallengeReuseConflict,receipts.ReceiptConflict,
            cas.CheckpointCASConflict,ValueError,OSError,
            TypeError,KeyError,IndexError):
        outcome['challenge_incident_conflict']=True
        status=1
    print(json.dumps(outcome,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
