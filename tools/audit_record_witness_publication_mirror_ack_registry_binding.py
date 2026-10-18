"""Stage 264T: match two independent local mirror-ack nonce-ledger copies
against every completed Stage 264S Ed25519 acknowledgment.

This read-only audit proves pinned duplicate LOCAL histories and that each
'complete' event corresponds to one enrolled, authentic, exact-byte-pinned
Stage 264Q envelope matching the earlier pre-sign body commitment. Pending
reservations remain pending. This does NOT prove live Stage 264P inspection,
global cross-host nonce CAS, independently retained pins or custody.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_mirror_ack_nonce_guard as guard
    from . import audit_record_witness_publication_signed_mirror_acknowledgments as mirror
    from . import audit_record_witness_publication_attestation_registry_binding as binding
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed
except ImportError:
    import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_mirror_ack_nonce_guard as guard
    import audit_record_witness_publication_signed_mirror_acknowledgments as mirror
    import audit_record_witness_publication_attestation_registry_binding as binding
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed

SCHEMA='wild-arms-ps1-mirrored-mirror-ack-signed-ledger-audit-v1'


class MirrorAckLedgerConflict(cross.LedgerDivergence):
    """Unable to establish complete, signed and enrolled mirror-ack history."""


def _envelope(raw,pin,*,reserve,completion,enrollment,scope,public):
    cas.digest(pin)
    if (type(raw) is not bytes or not 0<len(raw)<=mirror.MAX_SIGNED
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)
            or not hmac.compare_digest(pin,completion['receipt_sha256'])):
        raise MirrorAckLedgerConflict('signed acknowledgment mismatches exact external pin')
    role=reserve['role']
    pem_pin=enrollment[role]['public_pin']
    receipts._enrolled_pem(public,pem_pin)
    signed=_signed(raw,mirror.SCHEMA,mirror.DOMAIN,pem_pin,public)
    if type(signed) is not dict or set(signed)!=mirror.BODY_FIELDS:
        raise MirrorAckLedgerConflict('malformed or extra signed acknowledgment fields')
    count=signed.get('verified_signed_completion_count')
    events=signed.get('verified_event_count')
    pending=signed.get('pending_operator_roles')
    if (type(count) is not int or not 1<=count<=ledger.MAX_EVENTS
            or type(events) is not int or not count<=events<=ledger.MAX_EVENTS
            or type(pending) is not list or len(pending)>2
            or pending!=[r for r in ledger.ROLES if r in pending]):
        raise MirrorAckLedgerConflict('invalid signed mirror summary claim')
    for digest in ('primary_genesis_sha256','secondary_genesis_sha256',
                   'primary_head_sha256','secondary_head_sha256',
                   'exact_signed_completion_manifest_sha256'):
        cas.digest(signed[digest])
    audit={
        'schema':binding.SCHEMA,
        'every_completed_event_binds_pinned_ed25519_attestation':True,
        'all_ed25519_signatures_bind_canonical_pre_sign_body':True,
        'verified_signed_completion_count':count,
        'verified_event_count':events,
        'pending_operator_roles':pending,
    }
    expected=mirror.expected_body(audit,scope=scope,audit_id=signed['audit_id'],
        operator_role=role,operator_id=enrollment[role]['operator_id'],
        challenge=reserve['nonce'],sequence=reserve['sequence'],
        previous_sha256=reserve['prior_receipt_sha256'],
        genesis_a=signed['primary_genesis_sha256'],
        genesis_b=signed['secondary_genesis_sha256'],
        head_a=signed['primary_head_sha256'],
        head_b=signed['secondary_head_sha256'],
        manifest_sha256=signed['exact_signed_completion_manifest_sha256'])
    if (signed!=expected
            or reserve['archive_sha256']!=expected['exact_signed_completion_manifest_sha256']
            or reserve['evidence_sha256']!=guard.commitment(expected)
            or any(reserve[k]!=completion[k] for k in (
                'role','nonce','sequence','prior_receipt_sha256',
                'archive_sha256','evidence_sha256'))):
        raise MirrorAckLedgerConflict('signature fails pre-sign reservation binding')
    return True


def _completed(events,enrollment,scope,ack_envelopes,publics):
    if (type(ack_envelopes) is not dict
            or set(ack_envelopes)!=set(ledger.ROLES)
            or type(publics) is not dict or set(publics)!=set(ledger.ROLES)):
        raise MirrorAckLedgerConflict('both enrolled operators required')
    next_index={r:0 for r in ledger.ROLES}
    outstanding={r:None for r in ledger.ROLES}
    completed=0
    for row in events:
        event=dict(zip(ledger.FIELDS,row))
        role=event['role']
        if event['kind']=='reserve':
            if outstanding[role] is not None:
                raise MirrorAckLedgerConflict('double outstanding reserve')
            outstanding[role]=event
            continue
        before=outstanding[role]
        items=ack_envelopes[role]
        if (before is None or type(items) not in (list,tuple)
                or next_index[role]>=len(items)):
            raise MirrorAckLedgerConflict('completed acknowledgment has no signed envelope')
        pair=items[next_index[role]]
        if (type(pair) is not tuple or len(pair)!=2
                or type(pair[0]) is not bytes or type(pair[1]) is not str):
            raise MirrorAckLedgerConflict('bad signed envelope manifest shape')
        _envelope(pair[0],pair[1],reserve=before,completion=event,
                  enrollment=enrollment,scope=scope,public=publics[role])
        completed+=1
        next_index[role]+=1
        outstanding[role]=None
    for role in ledger.ROLES:
        if (type(ack_envelopes[role]) not in (list,tuple)
                or len(ack_envelopes[role])!=next_index[role]):
            raise MirrorAckLedgerConflict('extra or duplicated signed acknowledgment')
    if completed<1:
        raise MirrorAckLedgerConflict('no signed completed acknowledgment proven')
    return completed,[r for r in ledger.ROLES if outstanding[r] is not None]


def verify(primary,secondary,*,primary_head_pin,secondary_head_pin,
           primary_genesis_pin,secondary_genesis_pin,scope,
           operator_a_public,operator_b_public,signed_envelopes):
    """Whole local chain audits enclose independent Ed25519 receipt validation."""
    identities=cross._two_identities(primary,secondary)
    args=dict(primary_head_pin=primary_head_pin,
              secondary_head_pin=secondary_head_pin,
              primary_genesis_pin=primary_genesis_pin,
              secondary_genesis_pin=secondary_genesis_pin,
              expected_scope=scope)
    matched=cross.verify(primary,secondary,**args)
    a=cross._read_once(primary,expected_scope=scope,
                       expected_genesis=primary_genesis_pin,
                       expected_head=primary_head_pin)
    b=cross._read_once(secondary,expected_scope=scope,
                       expected_genesis=secondary_genesis_pin,
                       expected_head=secondary_head_pin)
    if (a['events']!=b['events'] or a['enrollment']!=b['enrollment']
            or cross._two_identities(primary,secondary)!=identities):
        raise MirrorAckLedgerConflict('two mirrored acknowledgment registries changed')
    count,pending=_completed(a['events'],a['enrollment'],scope,
        signed_envelopes,{'operator-a':operator_a_public,'operator-b':operator_b_public})
    again=cross.verify(primary,secondary,**args)
    if again!=matched or cross._two_identities(primary,secondary)!=identities:
        raise MirrorAckLedgerConflict('acknowledgment registry changed during signature audit')
    return {
        'schema':SCHEMA,
        'two_private_local_acknowledgment_ledgers_match':True,
        'all_completed_acknowledgment_signatures_bind_pre_sign_reservations':True,
        'two_full_registry_audits_enclosed_signature_checks':True,
        'verified_completed_acknowledgment_count':count,
        'pending_operator_roles':pending,
        'verified_event_count':matched['event_count'],
        'acknowledgment_ledger_head_sha256':matched['latest_ledger_sha256'],
        'independent_offhost_registry_retention_proved':False,
        'independently_trusted_external_pins_proved':False,
        'underlying_source_mirror_audits_replayed_proved':False,
        'remote_global_nonce_consensus_proved':False,
        'physical_operator_independence_proved':False,
        'automatic_registry_sync_authorized':False,
        'automatic_pending_recovery_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('primary',type=Path)
    p.add_argument('secondary',type=Path)
    for key in ('primary-head-pin','secondary-head-pin',
                'primary-genesis-pin','secondary-genesis-pin','scope'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--operator-a-public',type=Path,required=True)
    p.add_argument('--operator-b-public',type=Path,required=True)
    p.add_argument('--private-signed-manifest',type=Path,required=True)
    a=p.parse_args(argv)
    out={'schema':SCHEMA,'automatic_registry_sync_authorized':False,
         'automatic_pending_recovery_authorized':False,
         'automatic_cas_retry_authorized':False,
         'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False}
    try:
        out.update(verify(a.primary,a.secondary,
            primary_head_pin=a.primary_head_pin,
            secondary_head_pin=a.secondary_head_pin,
            primary_genesis_pin=a.primary_genesis_pin,
            secondary_genesis_pin=a.secondary_genesis_pin,
            scope=a.scope,operator_a_public=a.operator_a_public,
            operator_b_public=a.operator_b_public,
            signed_envelopes=binding._load_manifest(a.private_signed_manifest)))
        status=0
    except (MirrorAckLedgerConflict,cross.LedgerDivergence,
            ledger.NonceLedgerConflict,cas.CheckpointCASConflict,
            ValueError,TypeError,KeyError,IndexError,OSError,sqlite3.DatabaseError):
        out['acknowledgment_mirror_signature_conflict']=True
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
