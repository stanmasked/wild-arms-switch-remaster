"""Stage 264S: local atomic pre-sign guard for mirror-audit acknowledgments.

The already independently pinned Stage 264P full mirror/signature audit
completes BEFORE writing a private 264J reserve transaction. A distinct
acknowledgment-only enrolled nonce registry MUST exist, with an externally
retained current SHA-256. Full canonical Stage 264Q expected signed body is
committed in the reservation. A failed or ambiguous Ed25519 signature stays
pending forever without automatic clearing or retry.

This is one-host exclusion: no cross-host consensus, independent custody,
monotonic off-host authority, or authorization to retire witness fences.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_signed_mirror_acknowledgments as mirror
    from . import audit_record_witness_publication_attestation_registry_binding as binding
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _sign, _signed
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_anchor_handoff import _canonical
except ImportError:
    import audit_record_witness_publication_signed_mirror_acknowledgments as mirror
    import audit_record_witness_publication_attestation_registry_binding as binding
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _sign, _signed
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_anchor_handoff import _canonical

SCHEMA='wild-arms-ps1-mirror-ack-pre-sign-guard-v1'
REPORT_SCHEMA='wild-arms-ps1-mirror-ack-pre-sign-report-v1'
DOMAIN=b'wild-arms-ps1-mirror-ack-pre-sign-guard-v1\x00'


class MirrorGuardConflict(mirror.SignedMirrorConflict):
    """The signed mirror acknowledgment is not safely reserved or committed."""


def commitment(body):
    if (type(body) is not dict or set(body)!=mirror.BODY_FIELDS
            or body.get('schema')!=mirror.SCHEMA):
        raise MirrorGuardConflict('expected whole signed acknowledgment body missing')
    return hashlib.sha256(DOMAIN+_canonical(body)).hexdigest()


def guarded_sign(primary,secondary,registry,*,signed_envelopes,
                 head_a,head_b,genesis_a,genesis_b,
                 scope,audit_id,role,operator_id,storage_id,
                 nonce,sequence,previous_ack_sha256,
                 public_a,public_b,signing_private,signing_public,
                 signing_public_pin,expected_registry_head,output):
    """Verify, reserve, sign, independently readback, commit. Never auto-retry."""
    receipts._tag(storage_id)
    receipts._enrolled_pem(signing_public,signing_public_pin)
    if role not in ledger.ROLES:
        raise MirrorGuardConflict('unregistered signer role')
    kwargs=dict(primary_head_pin=head_a,secondary_head_pin=head_b,
                primary_genesis_pin=genesis_a,secondary_genesis_pin=genesis_b,
                scope=scope,operator_a_public=public_a,operator_b_public=public_b,
                signed_envelopes=signed_envelopes)
    first=binding.verify(primary,secondary,**kwargs)
    manifest=mirror.manifest_digest(signed_envelopes)
    source=binding.cross._read_once(primary,expected_scope=scope,
                                   expected_genesis=genesis_a,
                                   expected_head=head_a)['enrollment']
    enrolled=source[role]
    if (enrolled['operator_id']!=operator_id
            or enrolled['public_pin']!=signing_public_pin
            or (role=='operator-a' and
                Path(signing_public).read_bytes()!=Path(public_a).read_bytes())
            or (role=='operator-b' and
                Path(signing_public).read_bytes()!=Path(public_b).read_bytes())):
        raise MirrorGuardConflict('signing key and ID differ from source enrollment')
    body=mirror.expected_body(first,scope=scope,audit_id=audit_id,
        operator_role=role,operator_id=operator_id,challenge=nonce,
        sequence=sequence,previous_sha256=previous_ack_sha256,
        genesis_a=genesis_a,genesis_b=genesis_b,head_a=head_a,head_b=head_b,
        manifest_sha256=manifest)
    full_commitment=commitment(body)
    # Stage 264J verifies a separate, deliberately enrolled acknowledgment
    # nonce registry and excludes simultaneous reserves on the same SQLite.
    reservation=dict(scope=scope,role=role,operator_id=operator_id,
        storage_id=storage_id,operator_public_pin=signing_public_pin,
        nonce=nonce,seq=sequence,previous=previous_ack_sha256,
        archive_pin=manifest,evidence_pin=full_commitment)
    reserved=ledger._record(registry,action='reserve',
                            expected_head=expected_registry_head,**reservation)
    # The source can change after reserve: then the nonce remains pending,
    # but no signature is permitted.
    if (binding.verify(primary,secondary,**kwargs)!=first
            or mirror.manifest_digest(signed_envelopes)!=manifest):
        raise MirrorGuardConflict('mirror changed after reservation')
    _sign(body,mirror.SCHEMA,mirror.DOMAIN,signing_private,output)
    raw=_read_limited(_private_regular_file(output),mirror.MAX_SIGNED)
    actual=_signed(raw,mirror.SCHEMA,mirror.DOMAIN,
                   signing_public_pin,signing_public)
    if actual!=body:
        raise MirrorGuardConflict('signed envelope body differs from reservation')
    pin=hashlib.sha256(raw).hexdigest()
    # A changed original must never be marked as a complete attestation.
    if binding.verify(primary,secondary,**kwargs)!=first:
        raise MirrorGuardConflict('mirrored state changed during signed acknowledgment')
    final=ledger._record(registry,action='complete',expected_head=reserved,
                         receipt_pin=pin,**reservation)
    return {
        'schema':REPORT_SCHEMA,
        'acknowledgment_sha256':pin,
        'signed_body_commitment_sha256':full_commitment,
        'exact_signed_manifest_sha256':manifest,
        'latest_ack_registry_sha256':final,
        'nonce_reserved_before_ed25519_signature':True,
        'signed_acknowledgment_reverified_before_completion':True,
        'mirror_full_signature_audit_ran_before_and_after_signing':True,
        'separately_retained_registry_head_proved':False,
        'globally_monotonic_cross_host_nonce_cas_proved':False,
        'independent_physical_operator_custody_proved':False,
        'automatic_pending_recovery_authorized':False,
        'automatic_register_sync_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('primary','secondary','ack_registry','output'):
        parser.add_argument(name,type=Path)
    parser.add_argument('--private-signed-manifest',type=Path,required=True)
    for name in ('head-a','head-b','genesis-a','genesis-b','scope',
                 'audit-id','operator-id','storage-id','nonce',
                 'previous-ack-sha256','signing-public-pin',
                 'expected-registry-head'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--role',choices=ledger.ROLES,required=True)
    parser.add_argument('--sequence',type=int,required=True)
    parser.add_argument('--public-a',type=Path,required=True)
    parser.add_argument('--public-b',type=Path,required=True)
    parser.add_argument('--signing-public',type=Path,required=True)
    parser.add_argument('--signing-private',type=Path,required=True)
    args=parser.parse_args(argv)
    report={'schema':REPORT_SCHEMA,'automatic_pending_recovery_authorized':False,
            'automatic_register_sync_authorized':False,
            'automatic_cas_retry_authorized':False,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        result=guarded_sign(args.primary,args.secondary,args.ack_registry,
            output=args.output,
            signed_envelopes=binding._load_manifest(args.private_signed_manifest),
            head_a=args.head_a,head_b=args.head_b,
            genesis_a=args.genesis_a,genesis_b=args.genesis_b,
            scope=args.scope,audit_id=args.audit_id,role=args.role,
            operator_id=args.operator_id,storage_id=args.storage_id,
            nonce=args.nonce,sequence=args.sequence,
            previous_ack_sha256=args.previous_ack_sha256,
            public_a=args.public_a,public_b=args.public_b,
            signing_private=args.signing_private,signing_public=args.signing_public,
            signing_public_pin=args.signing_public_pin,
            expected_registry_head=args.expected_registry_head)
        report.update(result)
        code=0
    except (MirrorGuardConflict,mirror.SignedMirrorConflict,
            binding.SignedLedgerConflict,ledger.NonceLedgerConflict,
            cas.CheckpointCASConflict,ValueError,TypeError,KeyError,
            IndexError,OSError,sqlite3.DatabaseError):
        report['guarded_mirror_acknowledgment_conflict']=True
        code=1
    print(json.dumps(report,sort_keys=True))
    return code


if __name__=='__main__':
    raise SystemExit(main())
