"""Stage 264H: two signed challenge-bound acknowledgments of fork archive copies.

An operator can sign a receipt only after exact-byte SHA-256 and full Stage
264F Ed25519 evidence readback. The offline verifier needs two independently
pinned receipt hashes, operator PEM pins, distinct nonces/storage IDs, and
revalidates both Stage 264G local copies around receipt verification.

Signed statements of local inspection are NOT proof of physical/off-host
custody, WORM, independent administration, honest freshness or durability.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_equivocation_archive as archive
    from . import audit_record_witness_publication_equivocation_replica as replica
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed, _sign
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_replay_head_checkpoint import TAG, HEX32, _public_key_identity
except ImportError:
    import audit_record_witness_publication_equivocation_archive as archive
    import audit_record_witness_publication_equivocation_replica as replica
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed, _sign
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_replay_head_checkpoint import TAG, HEX32, _public_key_identity

SCHEMA='wild-arms-ps1-equivocation-replica-signed-ack-v1'
REPORT_SCHEMA='wild-arms-ps1-equivocation-replica-two-ack-audit-v1'
DOMAIN=b'wild-arms-ps1-equivocation-replica-signed-ack-v1\x00'
MAX_RECEIPT=2048
BODY_FIELDS={
    'schema','operator_role','operator_id','storage_id','checkpoint_scope',
    'audit_id','challenge_nonce','receipt_sequence','previous_receipt_sha256',
    'archive_sha256','canonical_evidence_sha256','copy_inspection_performed',
    'external_physical_custody_proved','witness_fence_retirement_authorized',
}


class ReceiptConflict(replica.DualCopyConflict):
    """An expected independent signed archive inspection is not established."""


def _tag(x):
    if type(x) is not str or not TAG.fullmatch(x):
        raise ReceiptConflict('invalid enrolled scoped identifier')
    return x


def _nonce(x):
    if type(x) is not str or not HEX32.fullmatch(x):
        raise ReceiptConflict('invalid 128-bit challenge')
    return x


def _enrolled_pem(public,pin):
    cas.digest(pin)
    pem=_read_limited(_private_regular_file(public),4096)
    if not hmac.compare_digest(hashlib.sha256(pem).hexdigest(),pin):
        raise ReceiptConflict('changed operator public PEM pin')
    return _public_key_identity(public)


def _body(role,operator_id,storage_id,scope,audit_id,nonce,sequence,
          previous_receipt,archive_sha,evidence_sha):
    if role not in ('operator-a','operator-b'):
        raise ReceiptConflict('unrecognized storage operator role')
    for value in (operator_id,storage_id,scope,audit_id):
        _tag(value)
    _nonce(nonce)
    cas.number(sequence,cas.MAX_SEQUENCE,'new operator receipt sequence')
    if sequence < 1:
        raise ReceiptConflict('signed receipt sequence did not start at 1')
    for value in (previous_receipt,archive_sha,evidence_sha):
        cas.digest(value)
    return {
        'schema':SCHEMA,
        'operator_role':role,
        'operator_id':operator_id,
        'storage_id':storage_id,
        'checkpoint_scope':scope,
        'audit_id':audit_id,
        'challenge_nonce':nonce,
        'receipt_sequence':sequence,
        'previous_receipt_sha256':previous_receipt,
        'archive_sha256':archive_sha,
        'canonical_evidence_sha256':evidence_sha,
        'copy_inspection_performed':True,
        'external_physical_custody_proved':False,
        'witness_fence_retirement_authorized':False,
    }


def attest(path,*,role,operator_id,storage_id,scope,audit_id,nonce,
           receipt_sequence,previous_receipt_sha256,
           independent_archive_pin,independent_evidence_pin,
           evidence_operator_a_public,evidence_operator_a_pin,
           evidence_operator_b_public,evidence_operator_b_pin,
           receipt_signing_private,receipt_public,receipt_public_pin,
           output):
    """Sign one local inspected copy; never overwrite an existing receipt."""
    candidate=_body(role,operator_id,storage_id,scope,audit_id,nonce,
                    receipt_sequence,previous_receipt_sha256,
                    independent_archive_pin,independent_evidence_pin)
    _enrolled_pem(receipt_public,receipt_public_pin)
    # Distinct receipt signing roles MAY reuse neither evidence operator keys
    # as a physical independence proof nor a real remote service.
    # Sign only the actual archive scope, not a caller-selected arbitrary tag.
    raw=archive._read(path)
    parsed=json.loads(raw,object_pairs_hook=cas._unique_json_fields,
                      parse_constant=cas._reject_json_constant)
    if (type(parsed) is not dict or type(parsed.get('metadata')) is not dict
            or parsed['metadata'].get('scope') != scope):
        raise ReceiptConflict('archive enrollment scope mismatched')
    before=replica._identity(path)
    observed=archive.inspect(path,
        expected_archive_sha256=independent_archive_pin,
        expected_evidence_sha256=independent_evidence_pin,
        operator_a_public=evidence_operator_a_public,
        operator_b_public=evidence_operator_b_public,
        external_operator_a_pin=evidence_operator_a_pin,
        external_operator_b_pin=evidence_operator_b_pin)
    if (replica._identity(path) != before
            or archive._read(path) != raw
            or observed['canonical_evidence_sha256'] != independent_evidence_pin):
        raise ReceiptConflict('copy changed between signature audit and signing')
    _sign(candidate,SCHEMA,DOMAIN,receipt_signing_private,output)
    signed=_read_limited(_private_regular_file(output),MAX_RECEIPT)
    verified=_signed(signed,SCHEMA,DOMAIN,receipt_public_pin,receipt_public)
    if verified != candidate:
        raise ReceiptConflict('local receipt signed body changed on reread')
    return {
        'schema':REPORT_SCHEMA,
        'receipt_role':role,
        'receipt_envelope_sha256':hashlib.sha256(signed).hexdigest(),
        'signed_local_inspection_revalidated':True,
        'independently_retained_receipt_hash_proved':False,
        'actual_external_custody_proved':False,
        'physical_durability_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def verify(primary,secondary,signed_a,signed_b, *,
           expected_scope,expected_audit_id,
           expected_operator_a_id,expected_operator_b_id,
           expected_storage_a_id,expected_storage_b_id,
           challenge_a,challenge_b,
           previous_a_sha256,previous_b_sha256,
           previous_a_sequence,previous_b_sequence,
           receipt_a_public,receipt_a_public_pin,
           receipt_b_public,receipt_b_public_pin,
           receipt_a_envelope_pin,receipt_b_envelope_pin,
           primary_pin,secondary_pin,evidence_pin,
           evidence_operator_a_public,evidence_operator_a_pin,
           evidence_operator_b_public,evidence_operator_b_pin):
    """Verify two signed inspections and two full archives; never mutate them."""
    for x in (expected_scope,expected_audit_id,expected_operator_a_id,
              expected_operator_b_id,expected_storage_a_id,expected_storage_b_id):
        _tag(x)
    _nonce(challenge_a)
    _nonce(challenge_b)
    if (challenge_a == challenge_b
            or expected_operator_a_id == expected_operator_b_id
            or expected_storage_a_id == expected_storage_b_id):
        raise ReceiptConflict('same challenge/operator/storage ID across roles')
    for pin in (previous_a_sha256,previous_b_sha256,
                receipt_a_envelope_pin,receipt_b_envelope_pin):
        cas.digest(pin)
    cas.number(previous_a_sequence,cas.MAX_SEQUENCE-1,'prior A sequence')
    cas.number(previous_b_sequence,cas.MAX_SEQUENCE-1,'prior B sequence')
    actual_key_a=_enrolled_pem(receipt_a_public,receipt_a_public_pin)
    actual_key_b=_enrolled_pem(receipt_b_public,receipt_b_public_pin)
    if actual_key_a == actual_key_b:
        raise ReceiptConflict('receipt operators share an Ed25519 DER key')
    for raw,pin in ((signed_a,receipt_a_envelope_pin),
                    (signed_b,receipt_b_envelope_pin)):
        if (type(raw) is not bytes or not 0 < len(raw) <= MAX_RECEIPT
                or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
            raise ReceiptConflict('signed receipt bytes do not match independent pin')

    file_observation=replica.verify(
        primary,secondary,primary_pin=primary_pin,secondary_pin=secondary_pin,
        evidence_pin=evidence_pin,
        operator_a_public=evidence_operator_a_public,
        operator_b_public=evidence_operator_b_public,
        external_operator_a_pin=evidence_operator_a_pin,
        external_operator_b_pin=evidence_operator_b_pin)
    before=replica._separate(primary,secondary)
    bodies=[]
    for raw,public,public_pin,role,operator,storage,challenge,previous,sequence in (
            (signed_a,receipt_a_public,receipt_a_public_pin,'operator-a',
             expected_operator_a_id,expected_storage_a_id,challenge_a,
             previous_a_sha256,previous_a_sequence),
            (signed_b,receipt_b_public,receipt_b_public_pin,'operator-b',
             expected_operator_b_id,expected_storage_b_id,challenge_b,
             previous_b_sha256,previous_b_sequence)):
        body=_signed(raw,SCHEMA,DOMAIN,public_pin,public)
        expected=_body(role,operator,storage,expected_scope,expected_audit_id,
                       challenge,sequence+1,previous,primary_pin,evidence_pin)
        if type(body) is not dict or set(body) != BODY_FIELDS or body != expected:
            raise ReceiptConflict('signed receipt does not bind exact independent inputs')
        bodies.append(body)
    if replica._separate(primary,secondary) != before:
        raise ReceiptConflict('archive inode identity changed while checking receipts')
    refreshed=replica.verify(
        primary,secondary,primary_pin=primary_pin,secondary_pin=secondary_pin,
        evidence_pin=evidence_pin,
        operator_a_public=evidence_operator_a_public,
        operator_b_public=evidence_operator_b_public,
        external_operator_a_pin=evidence_operator_a_pin,
        external_operator_b_pin=evidence_operator_b_pin)
    if (refreshed != file_observation
            or replica._separate(primary,secondary) != before):
        raise ReceiptConflict('archive changed between receipt audit passes')
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_pinned_ed25519_receipt_operators_verified':True,
        'two_independently_pinned_envelope_sha256_verified':True,
        'two_distinct_challenges_and_storage_ids_verified':True,
        'both_receipt_sequences_strictly_advance':True,
        'both_receipts_bind_exact_archive_and_evidence_sha256':True,
        'two_local_archives_reverified_around_receipts':True,
        'receipt_a_sha256':receipt_a_envelope_pin,
        'receipt_b_sha256':receipt_b_envelope_pin,
        'archive_sha256':primary_pin,
        'canonical_evidence_sha256':evidence_pin,
        'external_operator_independence_proved':False,
        'external_challenge_freshness_proved':False,
        'physical_durability_proved':False,
        'externally_retained_latest_receipt_pins_proved':False,
        'no_concurrent_receipt_fork_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'automatic_cas_retry_authorized':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('verify',))
    p.add_argument('primary',type=Path)
    p.add_argument('secondary',type=Path)
    p.add_argument('--receipt-a',type=Path,required=True)
    p.add_argument('--receipt-b',type=Path,required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--audit-id',required=True)
    for letter in ('a','b'):
        p.add_argument('--operator-'+letter+'-id',required=True)
        p.add_argument('--storage-'+letter+'-id',required=True)
        p.add_argument('--challenge-'+letter,required=True)
        p.add_argument('--previous-'+letter+'-sha256',required=True)
        p.add_argument('--previous-'+letter+'-sequence',type=int,required=True)
        p.add_argument('--receipt-'+letter+'-public',type=Path,required=True)
        p.add_argument('--receipt-'+letter+'-public-pin',required=True)
        p.add_argument('--receipt-'+letter+'-envelope-pin',required=True)
    for x in ('primary','secondary','evidence'):
        p.add_argument('--'+x+'-pin',required=True)
    for letter in ('a','b'):
        p.add_argument('--evidence-operator-'+letter+'-public',
                       type=Path,required=True)
        p.add_argument('--evidence-operator-'+letter+'-pin',required=True)
    a=p.parse_args(argv)
    outcome={'schema':REPORT_SCHEMA,'witness_fence_retirement_authorized':False,
             'witness_fence_retired':False,'automatic_cas_retry_authorized':False}
    try:
        raws=[_read_limited(_private_regular_file(f),MAX_RECEIPT)
              for f in (a.receipt_a,a.receipt_b)]
        outcome.update(verify(
            a.primary,a.secondary,*raws,expected_scope=a.scope,
            expected_audit_id=a.audit_id,
            expected_operator_a_id=a.operator_a_id,
            expected_operator_b_id=a.operator_b_id,
            expected_storage_a_id=a.storage_a_id,
            expected_storage_b_id=a.storage_b_id,
            challenge_a=a.challenge_a,challenge_b=a.challenge_b,
            previous_a_sha256=a.previous_a_sha256,
            previous_b_sha256=a.previous_b_sha256,
            previous_a_sequence=a.previous_a_sequence,
            previous_b_sequence=a.previous_b_sequence,
            receipt_a_public=a.receipt_a_public,
            receipt_a_public_pin=a.receipt_a_public_pin,
            receipt_b_public=a.receipt_b_public,
            receipt_b_public_pin=a.receipt_b_public_pin,
            receipt_a_envelope_pin=a.receipt_a_envelope_pin,
            receipt_b_envelope_pin=a.receipt_b_envelope_pin,
            primary_pin=a.primary_pin,secondary_pin=a.secondary_pin,
            evidence_pin=a.evidence_pin,
            evidence_operator_a_public=a.evidence_operator_a_public,
            evidence_operator_a_pin=a.evidence_operator_a_pin,
            evidence_operator_b_public=a.evidence_operator_b_public,
            evidence_operator_b_pin=a.evidence_operator_b_pin))
        status=0
    except (ReceiptConflict,replica.DualCopyConflict,archive.EvidenceArchiveConflict,
            cas.CheckpointCASConflict,ValueError,OSError,TypeError,
            KeyError,IndexError,sqlite3.DatabaseError):
        outcome['receipt_conflict']=True
        status=1
    print(json.dumps(outcome,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
