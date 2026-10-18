"""Stage 264Q: two independently pinned Ed25519 inspection claims for a
fully signature-bound mirrored operator nonce registry.

Only verifies separately issued receipts; does NOT expose an unguarded
operational signing CLI. Actual operators must use independently controlled
key custody and a separately guarded signing/nonce process. Two enrolled
keys alone do NOT prove separate physical operators, external retention
or globally monotonic nonce state.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_attestation_registry_binding as bound
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_attestation_registry_binding as bound
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-two-operator-signed-mirror-audit-v1'
REPORT_SCHEMA='wild-arms-ps1-two-operator-mirror-audit-report-v1'
DOMAIN=b'wild-arms-ps1-two-operator-signed-mirror-audit-v1\x00'
MANIFEST_DOMAIN=b'wild-arms-ps1-two-operator-mirror-signed-envelopes-v1\x00'
MAX_SIGNED=4096
BODY_FIELDS=frozenset({
    'schema','checkpoint_scope','audit_id','operator_role','operator_id',
    'challenge_nonce','acknowledgment_sequence',
    'previous_acknowledgment_sha256',
    'primary_genesis_sha256','secondary_genesis_sha256',
    'primary_head_sha256','secondary_head_sha256',
    'exact_signed_completion_manifest_sha256',
    'verified_signed_completion_count','verified_event_count',
    'pending_operator_roles',
    'both_mirror_histories_and_signatures_audited',
    'independent_offhost_custody_proved',
    'automatic_register_sync_authorized',
    'witness_fence_retirement_authorized',
})


class SignedMirrorConflict(bound.SignedLedgerConflict):
    """Two separately pinned operator mirror-audit acknowledgments not proven."""


def manifest_digest(envelopes):
    """Commit to role-ordered exact independently supplied envelope SHA-256."""
    if type(envelopes) is not dict or set(envelopes)!=set(ledger.ROLES):
        raise SignedMirrorConflict('must supply both enrolled manifest roles')
    record={}
    for role in ledger.ROLES:
        items=envelopes[role]
        if type(items) not in (list,tuple) or len(items)>ledger.MAX_EVENTS:
            raise SignedMirrorConflict('invalid bounded signed manifest')
        hashes=[]
        for item in items:
            if (type(item) is not tuple or len(item)!=2
                    or type(item[0]) is not bytes or type(item[1]) is not str):
                raise SignedMirrorConflict('invalid signed manifest item')
            cas.digest(item[1])
            if not hmac.compare_digest(hashlib.sha256(item[0]).hexdigest(),item[1]):
                raise SignedMirrorConflict('manifest envelope differs from supplied exact pin')
            hashes.append(item[1])
        record[role]=hashes
    return hashlib.sha256(MANIFEST_DOMAIN+_canonical({
        'schema':SCHEMA,'roles':record,
    })).hexdigest()


def expected_body(audit,*,scope,audit_id,operator_role,operator_id,
                  challenge,sequence,previous_sha256,genesis_a,genesis_b,
                  head_a,head_b,manifest_sha256):
    for name in (scope,audit_id,operator_id):
        receipts._tag(name)
    if operator_role not in ledger.ROLES:
        raise SignedMirrorConflict('operator role is not enrolled')
    receipts._nonce(challenge)
    cas.number(sequence,cas.MAX_SEQUENCE,'acknowledgment sequence')
    if sequence<1:
        raise SignedMirrorConflict('acknowledgment sequence must strictly advance')
    for item in (previous_sha256,genesis_a,genesis_b,head_a,head_b,manifest_sha256):
        cas.digest(item)
    if (type(audit) is not dict
            or audit.get('schema')!=bound.SCHEMA
            or audit.get('every_completed_event_binds_pinned_ed25519_attestation') is not True
            or audit.get('all_ed25519_signatures_bind_canonical_pre_sign_body') is not True
            or type(audit.get('verified_signed_completion_count')) is not int
            or audit['verified_signed_completion_count']<1
            or type(audit.get('verified_event_count')) is not int
            or type(audit.get('pending_operator_roles')) is not list
            or any(role not in ledger.ROLES
                   for role in audit['pending_operator_roles'])):
        raise SignedMirrorConflict('no fully verified signed mirror report')
    return {
        'schema':SCHEMA,'checkpoint_scope':scope,'audit_id':audit_id,
        'operator_role':operator_role,'operator_id':operator_id,
        'challenge_nonce':challenge,
        'acknowledgment_sequence':sequence,
        'previous_acknowledgment_sha256':previous_sha256,
        'primary_genesis_sha256':genesis_a,'secondary_genesis_sha256':genesis_b,
        'primary_head_sha256':head_a,'secondary_head_sha256':head_b,
        'exact_signed_completion_manifest_sha256':manifest_sha256,
        'verified_signed_completion_count':audit['verified_signed_completion_count'],
        'verified_event_count':audit['verified_event_count'],
        'pending_operator_roles':audit['pending_operator_roles'],
        'both_mirror_histories_and_signatures_audited':True,
        'independent_offhost_custody_proved':False,
        'automatic_register_sync_authorized':False,
        'witness_fence_retirement_authorized':False,
    }


def verify(primary,secondary,ack_a,ack_b, *,
           scope,audit_id,head_a,head_b,genesis_a,genesis_b,
           operator_a_id,operator_b_id,public_a,public_b,
           nonce_a,nonce_b,sequence_a,sequence_b,previous_a,previous_b,
           ack_a_pin,ack_b_pin,signed_envelopes):
    """Two full 264P rounds enclose exact two-signature verification."""
    for name in (operator_a_id,operator_b_id):
        receipts._tag(name)
    if operator_a_id==operator_b_id or nonce_a==nonce_b:
        raise SignedMirrorConflict('distinct enrolled identities/challenges required')
    for pin in (ack_a_pin,ack_b_pin):
        cas.digest(pin)
    digest_manifest=manifest_digest(signed_envelopes)
    kwargs=dict(primary_head_pin=head_a,secondary_head_pin=head_b,
                primary_genesis_pin=genesis_a,secondary_genesis_pin=genesis_b,
                scope=scope,operator_a_public=public_a,operator_b_public=public_b,
                signed_envelopes=signed_envelopes)
    first=bound.verify(primary,secondary,**kwargs)
    expected=(
        expected_body(first,scope=scope,audit_id=audit_id,
            operator_role='operator-a',operator_id=operator_a_id,
            challenge=nonce_a,sequence=sequence_a,previous_sha256=previous_a,
            genesis_a=genesis_a,genesis_b=genesis_b,
            head_a=head_a,head_b=head_b,manifest_sha256=digest_manifest),
        expected_body(first,scope=scope,audit_id=audit_id,
            operator_role='operator-b',operator_id=operator_b_id,
            challenge=nonce_b,sequence=sequence_b,previous_sha256=previous_b,
            genesis_a=genesis_a,genesis_b=genesis_b,
            head_a=head_a,head_b=head_b,manifest_sha256=digest_manifest))
    # Public key identity is enrolled in BOTH Stage 264P mirror registries;
    # do not accept alternative keys here even if they have valid signatures.
    for raw,pin,public,body in (
            (ack_a,ack_a_pin,public_a,expected[0]),
            (ack_b,ack_b_pin,public_b,expected[1])):
        if (type(raw) is not bytes or not 0<len(raw)<=MAX_SIGNED
                or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
            raise SignedMirrorConflict('signed mirror receipt missing independent envelope pin')
        public_pin=hashlib.sha256(Path(public).read_bytes()).hexdigest()
        signed=_signed(raw,SCHEMA,DOMAIN,public_pin,public)
        if type(signed) is not dict or set(signed)!=BODY_FIELDS or signed!=body:
            raise SignedMirrorConflict('operator signed incorrect mirrored audit body')
    if expected[0]['operator_role']==expected[1]['operator_role']:
        raise SignedMirrorConflict('signed operator roles not distinct')
    last=bound.verify(primary,secondary,**kwargs)
    if last!=first or manifest_digest(signed_envelopes)!=digest_manifest:
        raise SignedMirrorConflict('mirrored state changed between signed checks')
    return {
        'schema':REPORT_SCHEMA,
        'two_independently_sha256_pinned_ed25519_mirror_receipts_verified':True,
        'both_signatures_bind_same_reaudited_full_mirror':True,
        'all_registered_signed_completions_reverified':True,
        'exact_signed_completion_manifest_sha256':digest_manifest,
        'receipt_a_sha256':ack_a_pin,'receipt_b_sha256':ack_b_pin,
        'verified_signed_completion_count':first['verified_signed_completion_count'],
        'verified_event_count':first['verified_event_count'],
        'primary_head_sha256':head_a,'secondary_head_sha256':head_b,
        'independent_offhost_signers_proved':False,
        'external_receipt_pin_retention_proved':False,
        'globally_unique_challenge_cas_proved':False,
        'both_signatures_made_after_actual_live_inspection_proved':False,
        'automatic_register_sync_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('primary',type=Path)
    p.add_argument('secondary',type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--audit-id',required=True)
    p.add_argument('--genesis-a',required=True)
    p.add_argument('--genesis-b',required=True)
    p.add_argument('--head-a',required=True)
    p.add_argument('--head-b',required=True)
    p.add_argument('--private-signed-manifest',type=Path,required=True)
    for name in ('a','b'):
        p.add_argument('--ack-'+name,type=Path,required=True)
        p.add_argument('--ack-'+name+'-pin',required=True)
        p.add_argument('--public-'+name,type=Path,required=True)
        p.add_argument('--operator-'+name+'-id',required=True)
        p.add_argument('--nonce-'+name,required=True)
        p.add_argument('--sequence-'+name,type=int,required=True)
        p.add_argument('--previous-'+name+'-sha256',required=True)
    a=p.parse_args(argv)
    out={'schema':REPORT_SCHEMA,
         'automatic_register_sync_authorized':False,
         'automatic_cas_retry_authorized':False,
         'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False}
    try:
        envelopes=bound._load_manifest(a.private_signed_manifest)
        ack_a=_read_limited(_private_regular_file(a.ack_a),MAX_SIGNED)
        ack_b=_read_limited(_private_regular_file(a.ack_b),MAX_SIGNED)
        out.update(verify(
            a.primary,a.secondary,ack_a,ack_b,
            scope=a.scope,audit_id=a.audit_id,
            head_a=a.head_a,head_b=a.head_b,
            genesis_a=a.genesis_a,genesis_b=a.genesis_b,
            operator_a_id=a.operator_a_id,operator_b_id=a.operator_b_id,
            public_a=a.public_a,public_b=a.public_b,
            nonce_a=a.nonce_a,nonce_b=a.nonce_b,
            sequence_a=a.sequence_a,sequence_b=a.sequence_b,
            previous_a=a.previous_a_sha256,previous_b=a.previous_b_sha256,
            ack_a_pin=a.ack_a_pin,ack_b_pin=a.ack_b_pin,
            signed_envelopes=envelopes))
        status=0
    except (SignedMirrorConflict,bound.SignedLedgerConflict,
            ledger.NonceLedgerConflict,cas.CheckpointCASConflict,
            ValueError,OSError,KeyError,IndexError,TypeError,
            sqlite3.DatabaseError):
        out['signed_mirror_audit_conflict']=True
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
