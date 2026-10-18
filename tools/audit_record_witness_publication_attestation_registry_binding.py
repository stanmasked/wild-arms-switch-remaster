"""Stage 264P: reconcile two local nonce-registry copies against signed outputs.

Both complete 264O SQLite histories must be identical and separately pinned
(Stage 264K). In addition, EVERY completed Stage 264O reservation must bind
one independently SHA-256-pinned Ed25519 Stage 264M envelope: same role,
challenge, sequence, predecessor, archive digest, operator enrollment and
canonical full-body commitment. Pending reservations have no receipt and
remain blocked. The check is read-only, fail-closed, no automatic merge.
A local two-copy audit is NOT distributed consensus or external custody.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    from . import audit_record_witness_publication_attestation_nonce_guard as guard
    from . import audit_record_witness_publication_nonce_divergence_attestations as attest
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    import audit_record_witness_publication_attestation_nonce_guard as guard
    import audit_record_witness_publication_nonce_divergence_attestations as attest
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-signed-attestation-mirrored-ledger-audit-v1'
MAX_SIGNED=attest.MAX_SIGNED


class SignedLedgerConflict(cross.LedgerDivergence):
    """An attestation ledger or its completed signatures cannot be trusted."""


def _envelope(raw,pin,*,enrollment,scope,expected_reserve,expected_completion,
              public):
    cas.digest(pin)
    if (type(raw) is not bytes or not 0<len(raw)<=MAX_SIGNED
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)
            or not hmac.compare_digest(expected_completion['receipt_sha256'],pin)):
        raise SignedLedgerConflict('signed receipt absent, mismatched or not pinned')
    role=expected_reserve['role']
    operator=enrollment[role]['operator_id']
    public_pin=enrollment[role]['public_pin']
    receipts._enrolled_pem(public,public_pin)
    signed=_signed(raw,attest.SCHEMA,attest.DOMAIN,public_pin,public)
    if type(signed) is not dict or set(signed)!=attest.BODY_FIELDS:
        raise SignedLedgerConflict('signed attestation has unexpected fields')
    if (signed.get('conflict_class') not in
            ('forked_hash_chains','strict_prefix_lag')
            or type(signed.get('common_verified_event_count')) is not int
            or signed['common_verified_event_count']<0):
        raise SignedLedgerConflict('invalid signed divergence classification')
    expected=attest._claim(
        role,operator,signed['audit_id'],
        expected_reserve['nonce'],expected_reserve['sequence'],
        expected_reserve['prior_receipt_sha256'],scope,
        expected_reserve['archive_sha256'],
        signed['primary_genesis_sha256'],
        signed['secondary_genesis_sha256'],
        signed['primary_head_sha256'],
        signed['secondary_head_sha256'],
        {'conflict_class':signed['conflict_class'],
         'common_verified_event_count':signed['common_verified_event_count']})
    if (signed!=expected
            or expected_reserve['evidence_sha256']!=guard._commitment(expected)
            or any(expected_reserve[k]!=expected_completion[k]
                for k in ('role','nonce','sequence','prior_receipt_sha256',
                          'archive_sha256','evidence_sha256'))):
        raise SignedLedgerConflict('signed body does not bind original reservation')
    return True


def _audit_completion_bindings(events,enrollment,scope,receipt_files,
                               operator_publics):
    """Match every completed event to one private, independently pinned envelope."""
    if (type(receipt_files) is not dict
            or set(receipt_files)!=set(ledger.ROLES)):
        raise SignedLedgerConflict('complete role-to-envelope manifest required')
    if (type(operator_publics) is not dict
            or set(operator_publics)!=set(ledger.ROLES)):
        raise SignedLedgerConflict('complete role-to-public-PEM enrollment required')
    # The order is completion-event order within each role. No raw nonce or
    # absolute path is emitted in the success/failure report.
    index={role:0 for role in ledger.ROLES}
    pending={role:None for role in ledger.ROLES}
    completed=0
    for values in events:
        e=dict(zip(ledger.FIELDS,values))
        role=e['role']
        if e['kind']=='reserve':
            if pending[role] is not None:
                raise SignedLedgerConflict('nonmonotonic pending reservation')
            pending[role]=e
            continue
        reserve=pending[role]
        if reserve is None:
            raise SignedLedgerConflict('completion has no pending reservation')
        files=receipt_files[role]
        if type(files) not in (list,tuple) or index[role]>=len(files):
            raise SignedLedgerConflict('missing complete signed attestation evidence')
        item=files[index[role]]
        if (type(item) is not tuple or len(item)!=2 or
                type(item[0]) is not bytes or type(item[1]) is not str):
            raise SignedLedgerConflict('invalid exact-byte signed envelope record')
        _envelope(item[0],item[1],enrollment=enrollment,scope=scope,
                  expected_reserve=reserve,expected_completion=e,
                  public=operator_publics[role])
        index[role]+=1
        pending[role]=None
        completed+=1
    for role in ledger.ROLES:
        if (type(receipt_files[role]) not in (list,tuple)
                or len(receipt_files[role])!=index[role]):
            raise SignedLedgerConflict('extra or duplicated attestation envelopes')
    if completed<1:
        raise SignedLedgerConflict('no completed signature proven by external evidence')
    return completed,[role for role in ledger.ROLES if pending[role] is not None]


def verify(primary,secondary, *,
           primary_head_pin,secondary_head_pin,
           primary_genesis_pin,secondary_genesis_pin,scope,
           operator_a_public,operator_b_public,signed_envelopes):
    """Two-round per-registry audit enclosing exact receipt-to-reservation audit."""
    for value in (primary_head_pin,secondary_head_pin,
                  primary_genesis_pin,secondary_genesis_pin):
        cas.digest(value)
    before=cross._two_identities(primary,secondary)
    paired=cross.verify(primary,secondary,
        primary_head_pin=primary_head_pin,
        secondary_head_pin=secondary_head_pin,
        primary_genesis_pin=primary_genesis_pin,
        secondary_genesis_pin=secondary_genesis_pin,
        expected_scope=scope)
    one=cross._read_once(primary,expected_scope=scope,
                         expected_genesis=primary_genesis_pin,
                         expected_head=primary_head_pin)
    two=cross._read_once(secondary,expected_scope=scope,
                         expected_genesis=secondary_genesis_pin,
                         expected_head=secondary_head_pin)
    if (one['events']!=two['events'] or
            one['enrollment']!=two['enrollment'] or
            cross._two_identities(primary,secondary)!=before):
        raise SignedLedgerConflict('registry changed while checking signed outputs')
    completed,pending=_audit_completion_bindings(
        one['events'],one['enrollment'],scope,signed_envelopes,
        {'operator-a':operator_a_public,'operator-b':operator_b_public})
    # A late write/inode swap must not turn a previously audited clean
    # registry into an incorrectly signed or different "consensus".
    again=cross.verify(primary,secondary,
        primary_head_pin=primary_head_pin,
        secondary_head_pin=secondary_head_pin,
        primary_genesis_pin=primary_genesis_pin,
        secondary_genesis_pin=secondary_genesis_pin,
        expected_scope=scope)
    if (again!=paired or cross._two_identities(primary,secondary)!=before):
        raise SignedLedgerConflict('registry changed after signature audit')
    return {
        'schema':SCHEMA,
        'two_separately_pinned_full_nonce_chains_match':True,
        'every_completed_event_binds_pinned_ed25519_attestation':True,
        'all_ed25519_signatures_bind_canonical_pre_sign_body':True,
        'verified_signed_completion_count':completed,
        'pending_operator_roles':pending,
        'verified_event_count':paired['event_count'],
        'observed_ledger_head_sha256':paired['latest_ledger_sha256'],
        'two_local_registry_copies_audited':True,
        'globally_unique_nonce_registry_proved':False,
        'offhost_operator_independence_proved':False,
        'independent_retention_of_external_pins_proved':False,
        'actual_private_archive_inspection_proved':False,
        'atomic_cross_host_signing_proved':False,
        'automatic_register_sync_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def _load_manifest(path):
    """Private local JSON: role arrays of {path, sha256}; never show paths."""
    raw=_read_limited(_private_regular_file(path),65536)
    parsed=json.loads(raw,object_pairs_hook=cas._unique_json_fields,
                      parse_constant=cas._reject_json_constant)
    if type(parsed) is not dict or set(parsed)!=set(ledger.ROLES):
        raise SignedLedgerConflict('private envelope manifest must list both roles')
    out={}
    for role,items in parsed.items():
        if type(items) is not list or len(items)>ledger.MAX_EVENTS:
            raise SignedLedgerConflict('invalid signed envelope manifest length')
        out[role]=[]
        for item in items:
            if type(item) is not dict or set(item)!={'path','sha256'}:
                raise SignedLedgerConflict('unexpected signed envelope manifest fields')
            cas.digest(item['sha256'])
            if type(item['path']) is not str:
                raise SignedLedgerConflict('invalid signed envelope pathname')
            data=_read_limited(_private_regular_file(Path(item['path'])),MAX_SIGNED)
            out[role].append((data,item['sha256']))
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('primary',type=Path)
    p.add_argument('secondary',type=Path)
    p.add_argument('--primary-head-pin',required=True)
    p.add_argument('--secondary-head-pin',required=True)
    p.add_argument('--primary-genesis-pin',required=True)
    p.add_argument('--secondary-genesis-pin',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--operator-a-public',type=Path,required=True)
    p.add_argument('--operator-b-public',type=Path,required=True)
    p.add_argument('--private-signed-manifest',type=Path,required=True)
    args=p.parse_args(argv)
    out={'schema':SCHEMA,'automatic_register_sync_authorized':False,
         'automatic_cas_retry_authorized':False,
         'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False}
    try:
        out.update(verify(
            args.primary,args.secondary,
            primary_head_pin=args.primary_head_pin,
            secondary_head_pin=args.secondary_head_pin,
            primary_genesis_pin=args.primary_genesis_pin,
            secondary_genesis_pin=args.secondary_genesis_pin,
            scope=args.scope,operator_a_public=args.operator_a_public,
            operator_b_public=args.operator_b_public,
            signed_envelopes=_load_manifest(args.private_signed_manifest)))
        status=0
    except (SignedLedgerConflict,cross.LedgerDivergence,
            ledger.NonceLedgerConflict,cas.CheckpointCASConflict,
            ValueError,KeyError,TypeError,IndexError,OSError,
            sqlite3.DatabaseError):
        out['signed_registry_binding_conflict']=True
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
