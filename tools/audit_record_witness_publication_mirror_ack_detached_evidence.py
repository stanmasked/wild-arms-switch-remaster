"""Stage 264U: private create-only detached signed mirror-ack history evidence.

Create requires two fully independently pinned, locally distinct Stage 264S
acknowledgment ledgers and complete exact-byte-pinned Ed25519 envelopes.
Inspect does NOT need source SQLite files: both complete event chains replay
inside memory-only SQLite and every completed signature is authenticated.
The private archive contains raw nonce values and full signed envelopes:
NEVER upload it to a public GitHub repository. A local archive is not WORM,
remote custody, a global nonce CAS or proof of independent operators.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import stat
from pathlib import Path
import sqlite3

try:
    from . import audit_record_witness_publication_mirror_ack_registry_binding as bound
    from . import audit_record_witness_publication_receipt_nonce_divergence_evidence as detached
    from . import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_equivocation_archive as private
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_anchor_handoff import _canonical
except ImportError:
    import audit_record_witness_publication_mirror_ack_registry_binding as bound
    import audit_record_witness_publication_receipt_nonce_divergence_evidence as detached
    import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_equivocation_archive as private
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_anchor_handoff import _canonical

SCHEMA='wild-arms-ps1-mirror-ack-detached-full-signed-history-v1'
REPORT_SCHEMA='wild-arms-ps1-mirror-ack-detached-replay-report-v1'
FIELDS=frozenset(('schema','scope','primary_genesis_sha256',
                  'secondary_genesis_sha256','primary_head_sha256',
                  'secondary_head_sha256','primary','secondary','envelopes'))
SIGNATURE_FIELDS=frozenset(('raw_base64','sha256'))


class OfflineMirrorEvidenceConflict(bound.MirrorAckLedgerConflict):
    """Detached signed mirror evidence cannot be independently replayed."""


def _encode_envelopes(items):
    if type(items) is not dict or set(items)!=set(ledger.ROLES):
        raise OfflineMirrorEvidenceConflict('two enrolled envelope roles required')
    result={}
    for role in ledger.ROLES:
        values=items[role]
        if type(values) not in (list,tuple) or len(values)>ledger.MAX_EVENTS:
            raise OfflineMirrorEvidenceConflict('unbounded envelope manifest')
        packed=[]
        for pair in values:
            if (type(pair) is not tuple or len(pair)!=2
                    or type(pair[0]) is not bytes or type(pair[1]) is not str):
                raise OfflineMirrorEvidenceConflict('invalid envelope pair')
            raw,pin=pair
            cas.digest(pin)
            if (not 0<len(raw)<=bound.mirror.MAX_SIGNED
                    or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
                raise OfflineMirrorEvidenceConflict('signed envelope pin mismatch')
            packed.append({'raw_base64':base64.b64encode(raw).decode('ascii'),
                           'sha256':pin})
        result[role]=packed
    return result


def _decode_envelopes(packed):
    if type(packed) is not dict or set(packed)!=set(ledger.ROLES):
        raise OfflineMirrorEvidenceConflict('bad detached envelope role set')
    result={}
    for role in ledger.ROLES:
        entries=packed[role]
        if type(entries) is not list or len(entries)>ledger.MAX_EVENTS:
            raise OfflineMirrorEvidenceConflict('invalid bounded envelope list')
        values=[]
        for entry in entries:
            if type(entry) is not dict or set(entry)!=SIGNATURE_FIELDS:
                raise OfflineMirrorEvidenceConflict('unexpected signed evidence fields')
            raw_text=entry['raw_base64']
            if (type(raw_text) is not str
                    or not 0<len(raw_text)<=2*bound.mirror.MAX_SIGNED):
                raise OfflineMirrorEvidenceConflict('invalid bounded base64 envelope')
            try:
                raw=base64.b64decode(raw_text,validate=True)
            except (ValueError,base64.binascii.Error) as exc:
                raise OfflineMirrorEvidenceConflict('invalid envelope encoding') from exc
            if base64.b64encode(raw).decode('ascii')!=raw_text:
                raise OfflineMirrorEvidenceConflict('noncanonical base64 envelope')
            cas.digest(entry['sha256'])
            if (not 0<len(raw)<=bound.mirror.MAX_SIGNED
                    or not hmac.compare_digest(
                        hashlib.sha256(raw).hexdigest(),entry['sha256'])):
                raise OfflineMirrorEvidenceConflict('envelope differs from enrolled pin')
            values.append((raw,entry['sha256']))
        result[role]=values
    return result


def _replay_data(data,*,scope,genesis_a,genesis_b,head_a,head_b,
                 operator_a_public,operator_b_public):
    for value in (genesis_a,genesis_b,head_a,head_b):
        cas.digest(value)
    ledger._tag(scope)
    if (type(data) is not dict or set(data)!=FIELDS
            or data['schema']!=SCHEMA or data['scope']!=scope
            or data['primary_genesis_sha256']!=genesis_a
            or data['secondary_genesis_sha256']!=genesis_b
            or data['primary_head_sha256']!=head_a
            or data['secondary_head_sha256']!=head_b):
        raise OfflineMirrorEvidenceConflict('detached evidence missing external trust bindings')
    a,rows_a=detached._replay(data['primary'],scope,genesis_a,head_a)
    b,rows_b=detached._replay(data['secondary'],scope,genesis_b,head_b)
    if (genesis_a!=genesis_b or head_a!=head_b
            or rows_a!=rows_b or a['enrollment']!=b['enrollment']):
        raise OfflineMirrorEvidenceConflict('two detached source histories are not identical')
    signed=_decode_envelopes(data['envelopes'])
    count,pending=bound._completed(rows_a,a['enrollment'],scope,
        signed,{'operator-a':operator_a_public,'operator-b':operator_b_public})
    return {'completed':count,'pending':pending,'event_count':len(rows_a),
            'head':head_a,
            # Not exported as claimed off-host custody. Used only to match
            # each stable PEM identity with the externally pinned genesis.
            'enrolled_public_pins':{
                role:a['enrollment'][role]['public_pin'] for role in ledger.ROLES}}


def _report(pin,review,*,created):
    return {
        'schema':REPORT_SCHEMA,'private_evidence_archive_sha256':pin,
        'full_detached_event_chains_replayed_in_memory':True,
        'every_completed_attestation_signature_reverified_offline':True,
        'two_enrolled_histories_match_independent_external_pins':True,
        'completed_signed_acknowledgment_count':review['completed'],
        'verified_event_count':review['event_count'],
        'pending_operator_roles':review['pending'],
        'exclusive_archive_creation_and_readback_verified':created,
        'independent_external_archive_sha256_retention_proved':False,
        'physically_independent_operator_custody_proved':False,
        'actual_source_mirror_inspections_replayed_proved':False,
        'global_nonce_cas_consensus_proved':False,
        'automatic_ledger_merge_authorized':False,
        'automatic_pending_recovery_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def _stable_archive_identity(path):
    """Observe private inode, timestamps and size around the entire offline audit.

    No standalone stat can prevent a privileged attacker changing and
    restoring a file; this complements, rather than replaces, the
    bounded O_NOFOLLOW/fstat path checks in detached._private_read.
    """
    safe=private._secure_parent(path)
    state=os.lstat(safe)
    if (not stat.S_ISREG(state.st_mode) or state.st_nlink!=1
            or state.st_uid!=os.getuid() or state.st_mode&0o077):
        raise OfflineMirrorEvidenceConflict('archive identity no longer private')
    return (state.st_dev,state.st_ino,state.st_size,state.st_mode,
            state.st_nlink,state.st_uid,state.st_mtime_ns,state.st_ctime_ns)


def _stable_public_pem(path):
    """Owner-private PEM inode and exact bytes; refuse replacement mid-read."""
    initial=_stable_archive_identity(path)
    if not 0<initial[2]<=4096:
        raise OfflineMirrorEvidenceConflict('invalid bounded enrolled PEM size')
    raw=detached._private_read(path)
    if len(raw)!=initial[2] or _stable_archive_identity(path)!=initial:
        raise OfflineMirrorEvidenceConflict('enrolled public PEM changed while reading')
    return (initial,raw)


def _confirm_operator_pems(snapshots,operator_a_public,operator_b_public,
                           enrolled_pins):
    for role,path in (('operator-a',operator_a_public),
                      ('operator-b',operator_b_public)):
        before,raw=snapshots[role]
        if (not hmac.compare_digest(
                hashlib.sha256(raw).hexdigest(),enrolled_pins[role])
                or _stable_public_pem(path)!=(before,raw)):
            raise OfflineMirrorEvidenceConflict(
                'enrolled public PEM changed during full replay')


def inspect(path,*,archive_pin,scope,genesis_a,genesis_b,head_a,head_b,
            operator_a_public,operator_b_public):
    cas.digest(archive_pin)
    operator_snapshots={
        'operator-a':_stable_public_pem(operator_a_public),
        'operator-b':_stable_public_pem(operator_b_public)}
    initial=_stable_archive_identity(path)
    raw=detached._private_read(path)
    pin=hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(pin,archive_pin):
        raise OfflineMirrorEvidenceConflict('detached archive SHA-256 not externally pinned')
    try:
        obj=json.loads(raw,object_pairs_hook=cas._unique_json_fields,
                       parse_constant=cas._reject_json_constant)
    except (ValueError,UnicodeError) as exc:
        raise OfflineMirrorEvidenceConflict('invalid canonical unique-key archive') from exc
    if raw!=_canonical(obj):
        raise OfflineMirrorEvidenceConflict('noncanonical detached archive JSON')
    result=_replay_data(obj,scope=scope,genesis_a=genesis_a,
        genesis_b=genesis_b,head_a=head_a,head_b=head_b,
        operator_a_public=operator_a_public,operator_b_public=operator_b_public)
    # A PEM can be replaced mid-verification just as the archive can.
    # Enrollment pins are bound to the externally checked registry genesis.
    # Rechecking BOTH operator keys also covers an enrolled role without
    # any completed signature in this particular archive.
    _confirm_operator_pems(
        operator_snapshots,operator_a_public,operator_b_public,
        result['enrolled_public_pins'])
    # Revalidate the actual path and exact private bytes *after* all chain
    # and Ed25519 checks, catching file replacement during verification
    # even if the original first read was correctly pinned.
    if (_stable_archive_identity(path)!=initial
            or detached._private_read(path)!=raw
            or _stable_archive_identity(path)!=initial):
        raise OfflineMirrorEvidenceConflict('archive changed during offline verification')
    return _report(pin,result,created=False)


def create(output,primary,secondary,*,signed_envelopes,
           scope,genesis_a,genesis_b,head_a,head_b,
           operator_a_public,operator_b_public):
    kwargs=dict(primary_head_pin=head_a,secondary_head_pin=head_b,
        primary_genesis_pin=genesis_a,secondary_genesis_pin=genesis_b,
        scope=scope,operator_a_public=operator_a_public,
        operator_b_public=operator_b_public,signed_envelopes=signed_envelopes)
    identities=cross._two_identities(primary,secondary)
    original=bound.verify(primary,secondary,**kwargs)
    left=cross._read_once(primary,expected_scope=scope,
        expected_genesis=genesis_a,expected_head=head_a)
    right=cross._read_once(secondary,expected_scope=scope,
        expected_genesis=genesis_b,expected_head=head_b)
    if (left['events']!=right['events'] or left['enrollment']!=right['enrollment']
            or cross._two_identities(primary,secondary)!=identities):
        raise OfflineMirrorEvidenceConflict('source changed during evidence collection')
    data={
        'schema':SCHEMA,'scope':scope,
        'primary_genesis_sha256':genesis_a,
        'secondary_genesis_sha256':genesis_b,
        'primary_head_sha256':head_a,'secondary_head_sha256':head_b,
        'primary':{'enrollment':left['enrollment'],
                   'events':[list(x) for x in left['events']]},
        'secondary':{'enrollment':right['enrollment'],
                     'events':[list(x) for x in right['events']]},
        'envelopes':_encode_envelopes(signed_envelopes),
    }
    reviewed=_replay_data(data,scope=scope,genesis_a=genesis_a,
        genesis_b=genesis_b,head_a=head_a,head_b=head_b,
        operator_a_public=operator_a_public,operator_b_public=operator_b_public)
    final=bound.verify(primary,secondary,**kwargs)
    if (final!=original
            or cross._two_identities(primary,secondary)!=identities):
        raise OfflineMirrorEvidenceConflict('source changed during detached archive creation')
    raw=_canonical(data)
    if not 0<len(raw)<=detached.MAX_BYTES:
        raise OfflineMirrorEvidenceConflict('detached private archive exceeds bounded size')
    pin=hashlib.sha256(raw).hexdigest()
    private._write_exclusive(output,raw)
    rechecked=inspect(output,archive_pin=pin,scope=scope,
        genesis_a=genesis_a,genesis_b=genesis_b,head_a=head_a,head_b=head_b,
        operator_a_public=operator_a_public,operator_b_public=operator_b_public)
    if rechecked['completed_signed_acknowledgment_count']!=reviewed['completed']:
        raise OfflineMirrorEvidenceConflict('readback replay differs from inspected bytes')
    return _report(pin,reviewed,created=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('create','inspect'))
    p.add_argument('archive',type=Path)
    p.add_argument('--primary',type=Path)
    p.add_argument('--secondary',type=Path)
    p.add_argument('--archive-pin')
    for name in ('scope','genesis-a','genesis-b','head-a','head-b'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--operator-a-public',type=Path,required=True)
    p.add_argument('--operator-b-public',type=Path,required=True)
    p.add_argument('--private-signed-manifest',type=Path)
    a=p.parse_args(argv)
    opts=dict(scope=a.scope,genesis_a=a.genesis_a,genesis_b=a.genesis_b,
        head_a=a.head_a,head_b=a.head_b,operator_a_public=a.operator_a_public,
        operator_b_public=a.operator_b_public)
    result={'schema':REPORT_SCHEMA,'automatic_ledger_merge_authorized':False,
        'automatic_pending_recovery_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False}
    try:
        if a.action=='create':
            if (a.primary is None or a.secondary is None
                    or a.private_signed_manifest is None or a.archive_pin is not None):
                raise OfflineMirrorEvidenceConflict('missing required private source ledger or manifest')
            answer=create(a.archive,a.primary,a.secondary,
                signed_envelopes=bound.binding._load_manifest(a.private_signed_manifest),
                **opts)
        else:
            if a.archive_pin is None:
                raise OfflineMirrorEvidenceConflict('separate independent exact archive SHA-256 required')
            answer=inspect(a.archive,archive_pin=a.archive_pin,**opts)
        result.update(answer)
        status=0
    except (OfflineMirrorEvidenceConflict,bound.MirrorAckLedgerConflict,
            cross.LedgerDivergence,cas.CheckpointCASConflict,
            ValueError,KeyError,IndexError,TypeError,OSError,sqlite3.DatabaseError):
        result['detached_signed_mirror_evidence_conflict']=True
        status=1
    print(json.dumps(result,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
