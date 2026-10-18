"""Stages 264M–264O: two Ed25519 acknowledgments of independently pinned nonce-fork evidence.

Each operator signs a *separate, offline inspection claim* about the same
fully re-audited Stage 264L private artifact. Verification requires exact
external SHA-256 pins for both signed envelopes and the artifact, two enrolled
distinct Ed25519 PEM keys, exact archived ledger head/genesis pins, two
separate expected challenges, prior attestation pins and sequences.

Neither two valid signatures nor two local paths establish real physical
off-host custody, WORM, global latestness, receipt/nonce CAS, or honesty.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_receipt_nonce_divergence_evidence as evidence
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _sign, _signed
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_receipt_nonce_divergence_evidence as evidence
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _sign, _signed
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-nonce-divergence-two-operator-attestation-v1'
REPORT_SCHEMA='wild-arms-ps1-nonce-divergence-attestation-report-v1'
DOMAIN=b'wild-arms-ps1-nonce-divergence-two-operator-attestation-v1\x00'
MAX_SIGNED=4096
BODY_FIELDS=frozenset({
    'schema','operator_role','operator_id','audit_id','checkpoint_scope',
    'challenge_nonce','sequence','previous_attestation_sha256',
    'archive_sha256','primary_genesis_sha256','secondary_genesis_sha256',
    'primary_head_sha256','secondary_head_sha256','conflict_class',
    'common_verified_event_count','archive_inspection_performed',
    'external_independent_custody_proved','automatic_ledger_merge_authorized',
    'witness_fence_retirement_authorized',
})


class AttestationConflict(evidence.DetachedHistoryConflict):
    """Two distinct pinned, complete signed attestations not established."""


def _trusted(scope,audit_id,nonce,sequence,previous_pin):
    for v in (scope,audit_id):
        receipts._tag(v)
    receipts._nonce(nonce)
    cas.number(sequence,cas.MAX_SEQUENCE,'attestation sequence')
    if sequence<1:
        raise AttestationConflict('attestation sequence must be positive')
    cas.digest(previous_pin)


def _claim(role,operator_id,audit_id,nonce,sequence,previous_pin,scope,
           archive_pin,genesis_a,genesis_b,head_a,head_b,reviewed):
    if role not in ('operator-a','operator-b'):
        raise AttestationConflict('unexpected enrolled role')
    receipts._tag(operator_id)
    _trusted(scope,audit_id,nonce,sequence,previous_pin)
    for value in (archive_pin,genesis_a,genesis_b,head_a,head_b):
        cas.digest(value)
    if (type(reviewed) is not dict
            or reviewed.get('conflict_class') not in
               ('forked_hash_chains','strict_prefix_lag')
            or type(reviewed.get('common_verified_event_count')) is not int):
        raise AttestationConflict('missing verified detached divergence')
    return {
        'schema':SCHEMA,
        'operator_role':role,
        'operator_id':operator_id,
        'audit_id':audit_id,
        'checkpoint_scope':scope,
        'challenge_nonce':nonce,
        'sequence':sequence,
        'previous_attestation_sha256':previous_pin,
        'archive_sha256':archive_pin,
        'primary_genesis_sha256':genesis_a,
        'secondary_genesis_sha256':genesis_b,
        'primary_head_sha256':head_a,
        'secondary_head_sha256':head_b,
        'conflict_class':reviewed['conflict_class'],
        'common_verified_event_count':reviewed['common_verified_event_count'],
        'archive_inspection_performed':True,
        'external_independent_custody_proved':False,
        'automatic_ledger_merge_authorized':False,
        'witness_fence_retirement_authorized':False,
    }


def _inspect(path,scope,archive_pin,genesis_a,genesis_b,head_a,head_b):
    return evidence.inspect(path,external_archive_pin=archive_pin,
        expected_scope=scope,external_primary_genesis=genesis_a,
        external_secondary_genesis=genesis_b,
        external_primary_head=head_a,external_secondary_head=head_b)


def attest(path,*,role,operator_id,audit_id,nonce,sequence,previous_pin,
           scope,archive_pin,genesis_a,genesis_b,head_a,head_b,
           signing_private,public,public_pin,output):
    """Inspect actual private archive before no-replace Ed25519 signing."""
    receipts._enrolled_pem(public,public_pin)
    before=evidence._private_read(path)
    reviewed=_inspect(path,scope,archive_pin,genesis_a,genesis_b,head_a,head_b)
    if evidence._private_read(path)!=before:
        raise AttestationConflict('evidence archive changed during signed inspection')
    body=_claim(role,operator_id,audit_id,nonce,sequence,previous_pin,scope,
                archive_pin,genesis_a,genesis_b,head_a,head_b,reviewed)
    _sign(body,SCHEMA,DOMAIN,signing_private,output)
    raw=_read_limited(_private_regular_file(output),MAX_SIGNED)
    parsed=_signed(raw,SCHEMA,DOMAIN,public_pin,public)
    if parsed!=body:
        raise AttestationConflict('signed attestation readback mismatch')
    return {
        'schema':REPORT_SCHEMA,
        'signed_attestation_reverified':True,
        'attestation_envelope_sha256':hashlib.sha256(raw).hexdigest(),
        'archive_sha256':archive_pin,
        'external_independent_custody_proved':False,
        'independently_retained_attestation_pin_proved':False,
        'offhost_monotonic_attestation_cas_proved':False,
        'automatic_ledger_merge_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def verify(path,signed_a,signed_b,*,scope,audit_id,
           operator_a_id,operator_b_id,nonce_a,nonce_b,
           sequence_a,sequence_b,previous_a,previous_b,
           public_a,public_a_pin,public_b,public_b_pin,
           envelope_a_pin,envelope_b_pin,
           archive_pin,genesis_a,genesis_b,head_a,head_b):
    """Reverify complete archive around both exact external signed envelopes."""
    receipts._tag(scope)
    receipts._tag(audit_id)
    receipts._tag(operator_a_id)
    receipts._tag(operator_b_id)
    receipts._nonce(nonce_a)
    receipts._nonce(nonce_b)
    if operator_a_id==operator_b_id or nonce_a==nonce_b:
        raise AttestationConflict('duplicate operators or challenges')
    for pin in (envelope_a_pin,envelope_b_pin):
        cas.digest(pin)
    key_a=receipts._enrolled_pem(public_a,public_a_pin)
    key_b=receipts._enrolled_pem(public_b,public_b_pin)
    if key_a==key_b:
        raise AttestationConflict('two roles use the same Ed25519 DER key')
    for raw,pin in ((signed_a,envelope_a_pin),(signed_b,envelope_b_pin)):
        if (type(raw) is not bytes or not 0<len(raw)<=MAX_SIGNED
                or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
            raise AttestationConflict('signed envelope missing independent exact-byte pin')
    before=evidence._private_read(path)
    reviewed=_inspect(path,scope,archive_pin,genesis_a,genesis_b,head_a,head_b)
    for raw,role,op,nonce,seq,previous,public,pin in (
            (signed_a,'operator-a',operator_a_id,nonce_a,sequence_a,
             previous_a,public_a,public_a_pin),
            (signed_b,'operator-b',operator_b_id,nonce_b,sequence_b,
             previous_b,public_b,public_b_pin)):
        expected=_claim(role,op,audit_id,nonce,seq,previous,scope,
                        archive_pin,genesis_a,genesis_b,head_a,head_b,reviewed)
        claim=_signed(raw,SCHEMA,DOMAIN,pin,public)
        if type(claim) is not dict or set(claim)!=BODY_FIELDS or claim!=expected:
            raise AttestationConflict('signature claims contradict enrolled inspected archive')
    if (evidence._private_read(path)!=before
            or _inspect(path,scope,archive_pin,genesis_a,genesis_b,
                        head_a,head_b)!=reviewed):
        raise AttestationConflict('archive changed during two-party signed audit')
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_ed25519_operator_keys_verified':True,
        'two_independently_pinned_signed_attestations_verified':True,
        'both_signatures_bind_same_fully_replayed_archive':True,
        'separate_expected_nonce_and_previous_attestation_pins_verified':True,
        'archive_reread_and_offline_replay_completed':True,
        'archive_sha256':archive_pin,
        'attestation_a_sha256':envelope_a_pin,
        'attestation_b_sha256':envelope_b_pin,
        'conflict_class':reviewed['conflict_class'],
        'common_verified_event_count':reviewed['common_verified_event_count'],
        'external_independent_custody_proved':False,
        'independently_retained_attestation_pins_proved':False,
        'offhost_monotonic_attestation_cas_proved':False,
        'signed_operators_honest_proved':False,
        'global_latest_incident_proved':False,
        'automatic_ledger_merge_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('sign','verify'))
    p.add_argument('archive',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--audit-id',required=True)
    p.add_argument('--archive-pin',required=True)
    for field in ('primary-genesis','secondary-genesis',
                  'primary-head','secondary-head'):
        p.add_argument('--'+field+'-pin',required=True)
    p.add_argument('--role',choices=('operator-a','operator-b'))
    p.add_argument('--operator-id')
    p.add_argument('--challenge')
    p.add_argument('--sequence',type=int)
    p.add_argument('--previous-attestation-pin')
    p.add_argument('--signing-private',type=Path)
    p.add_argument('--attestation-registry',type=Path)
    p.add_argument('--expected-registry-head')
    p.add_argument('--storage-id')
    p.add_argument('--output',type=Path)
    p.add_argument('--signing-public',type=Path)
    p.add_argument('--signing-public-pin')
    for x in ('a','b'):
        p.add_argument('--operator-'+x+'-id')
        p.add_argument('--challenge-'+x)
        p.add_argument('--sequence-'+x,type=int)
        p.add_argument('--previous-'+x+'-sha256')
        p.add_argument('--public-'+x,type=Path)
        p.add_argument('--public-'+x+'-pin')
        p.add_argument('--receipt-'+x,type=Path)
        p.add_argument('--receipt-'+x+'-pin')
    a=p.parse_args(argv)
    trust=dict(scope=a.scope,archive_pin=a.archive_pin,
               genesis_a=a.primary_genesis_pin,
               genesis_b=a.secondary_genesis_pin,
               head_a=a.primary_head_pin,head_b=a.secondary_head_pin)
    result={'schema':REPORT_SCHEMA,'automatic_ledger_merge_authorized':False,
            'automatic_cas_retry_authorized':False,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        if a.action=='sign':
            if any(x is None for x in (a.role,a.operator_id,a.challenge,
                 a.sequence,a.previous_attestation_pin,a.signing_private,
                 a.signing_public,a.signing_public_pin,a.output,
                 a.attestation_registry,a.expected_registry_head,a.storage_id)):
                raise AttestationConflict('missing mandatory pre-sign enrollment')
            # Import inside the CLI entry only; guard imports this module.
            try:
                from . import audit_record_witness_publication_attestation_nonce_guard as guard
            except ImportError:
                import audit_record_witness_publication_attestation_nonce_guard as guard
            report=guard.guarded_attest(
                a.archive,a.attestation_registry,
                expected_registry_head=a.expected_registry_head,
                storage_id=a.storage_id,
                role=a.role,operator_id=a.operator_id,
                audit_id=a.audit_id,nonce=a.challenge,sequence=a.sequence,
                previous_pin=a.previous_attestation_pin,
                signing_private=a.signing_private,public=a.signing_public,
                public_pin=a.signing_public_pin,output=a.output,**trust)
        else:
            if any(x is None for x in (
                a.operator_a_id,a.operator_b_id,a.challenge_a,a.challenge_b,
                a.sequence_a,a.sequence_b,a.previous_a_sha256,a.previous_b_sha256,
                a.public_a,a.public_a_pin,a.public_b,a.public_b_pin,
                a.receipt_a,a.receipt_b,a.receipt_a_pin,a.receipt_b_pin)):
                raise AttestationConflict('missing independently enrolled two signed claims')
            raws=[_read_limited(_private_regular_file(x),MAX_SIGNED)
                  for x in (a.receipt_a,a.receipt_b)]
            report=verify(a.archive,*raws,audit_id=a.audit_id,
                operator_a_id=a.operator_a_id,operator_b_id=a.operator_b_id,
                nonce_a=a.challenge_a,nonce_b=a.challenge_b,
                sequence_a=a.sequence_a,sequence_b=a.sequence_b,
                previous_a=a.previous_a_sha256,
                previous_b=a.previous_b_sha256,
                public_a=a.public_a,public_a_pin=a.public_a_pin,
                public_b=a.public_b,public_b_pin=a.public_b_pin,
                envelope_a_pin=a.receipt_a_pin,
                envelope_b_pin=a.receipt_b_pin,**trust)
        result.update(report)
        status=0
    except (AttestationConflict,evidence.DetachedHistoryConflict,
            receipts.ReceiptConflict,cas.CheckpointCASConflict,
            ValueError,OSError,KeyError,TypeError,IndexError,sqlite3.DatabaseError):
        result['signed_evidence_attestation_conflict']=True
        status=1
    print(json.dumps(result,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
