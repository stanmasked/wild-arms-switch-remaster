"""Stage 264O: mandatory local pre-sign nonce reservation for 264M CLI.

Reuses the fully replayed Stage 264J transactional nonce ledger with a
SEPARATE enrolled registry/scope and a domain-separated commitment to every
field of the expected Stage 264M signed body. The reservation is atomically
committed BEFORE signing. Failed or ambiguous signatures remain pending and
cannot be retried. The implementation is a LOCAL signing guard, not a
distributed operator authority, WORM or externally managed CAS.
"""
import hashlib
import hmac
import sqlite3

try:
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_nonce_divergence_attestations as attest
    from . import audit_record_witness_publication_replica_receipts as receipts
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_nonce_divergence_attestations as attest
    import audit_record_witness_publication_replica_receipts as receipts
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-fork-attestation-pre-sign-guard-v1'
DOMAIN=b'wild-arms-ps1-fork-attestation-pre-sign-guard-v1\x00'
REPORT_SCHEMA='wild-arms-ps1-fork-attestation-pre-sign-report-v1'


class PreSignAttestationConflict(attest.AttestationConflict):
    """The enrolled pre-sign attestation reservation is not established."""


def _commitment(body):
    """Bind EVERY canonical attestation field (including audit and heads)."""
    if type(body) is not dict or set(body)!=attest.BODY_FIELDS or body['schema']!=attest.SCHEMA:
        raise PreSignAttestationConflict('invalid attestation body commitment')
    return hashlib.sha256(DOMAIN+_canonical(body)).hexdigest()


def guarded_attest(path,registry_path,*,storage_id,expected_registry_head,
                   role,operator_id,audit_id,nonce,sequence,previous_pin,
                   scope,archive_pin,genesis_a,genesis_b,head_a,head_b,
                   signing_private,public,public_pin,output):
    """Inspect; atomically consume attestation nonce; sign; complete exactly once."""
    receipts._tag(storage_id)
    receipts._enrolled_pem(public,public_pin)
    before=attest.evidence._private_read(path)
    reviewed=attest._inspect(path,scope,archive_pin,genesis_a,genesis_b,head_a,head_b)
    if attest.evidence._private_read(path)!=before:
        raise PreSignAttestationConflict('archive changed before reserved signing')
    claim=attest._claim(role,operator_id,audit_id,nonce,sequence,previous_pin,
                        scope,archive_pin,genesis_a,genesis_b,head_a,head_b,reviewed)
    record=dict(scope=scope,role=role,operator_id=operator_id,storage_id=storage_id,
                operator_public_pin=public_pin,nonce=nonce,seq=sequence,
                previous=previous_pin,archive_pin=archive_pin,
                evidence_pin=_commitment(claim))
    # Pending reservation is durable before _sign. Never undo it if
    # the signed output or completion acknowledgment becomes ambiguous.
    reserved=ledger._record(registry_path,action='reserve',
                            expected_head=expected_registry_head,**record)
    signed=attest.attest(path,role=role,operator_id=operator_id,audit_id=audit_id,
        nonce=nonce,sequence=sequence,previous_pin=previous_pin,
        scope=scope,archive_pin=archive_pin,genesis_a=genesis_a,genesis_b=genesis_b,
        head_a=head_a,head_b=head_b,signing_private=signing_private,
        public=public,public_pin=public_pin,output=output)
    raw=_read_limited(_private_regular_file(output),attest.MAX_SIGNED)
    reverified=_signed(raw,attest.SCHEMA,attest.DOMAIN,public_pin,public)
    if reverified!=claim:
        raise PreSignAttestationConflict('signed body does not match reserved commitment')
    envelope_pin=hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(envelope_pin,signed['attestation_envelope_sha256']):
        raise PreSignAttestationConflict('signed output differs from attested receipt')
    head=ledger._record(registry_path,action='complete',
                        expected_head=reserved,receipt_pin=envelope_pin,**record)
    return {
        **signed,'guard_schema':SCHEMA,'nonce_reserved_before_ed25519_signing':True,
        'signed_body_commitment_sha256':record['evidence_pin'],
        'signed_attestation_completed_once':True,
        'latest_attestation_registry_sha256':head,
        'independent_offhost_registry_head_retention_proved':False,
        'global_cross_host_nonce_uniqueness_proved':False,
        'automatic_pending_reservation_recovery_authorized':False,
    }
