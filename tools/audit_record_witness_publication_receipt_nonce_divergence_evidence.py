"""Stage 264L: detached, no-overwrite evidence of two diverged nonce histories.

Retains complete bounded Stage 264J event chains plus enrollment and their
separately supplied prior external genesis/head pins. Offline inspection
reconstructs both SQLite chains in RAM and runs the original Stage 264J
auditor. The artifact is PRIVATE: it contains raw nonces, IDs and digests.
No durable independent archive, operator signature or global CAS is proved.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat

try:
    from . import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_equivocation_archive as private
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_anchor_handoff import _canonical
except ImportError:
    import audit_record_witness_publication_receipt_nonce_reconciliation as cross
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_equivocation_archive as private
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_anchor_handoff import _canonical

SCHEMA='wild-arms-ps1-receipt-nonce-two-history-evidence-v1'
REPORT_SCHEMA='wild-arms-ps1-receipt-nonce-two-history-evidence-report-v1'
MAX_BYTES=4*1024*1024
FIELDS={'schema','scope','primary_genesis_sha256','secondary_genesis_sha256',
        'primary_head_sha256','secondary_head_sha256',
        'primary','secondary'}
BRANCH_FIELDS={'enrollment','events'}


class DetachedHistoryConflict(cross.LedgerDivergence):
    """The two detached pinned, audited nonce histories are not established."""


def _args_pins(primary_genesis,secondary_genesis,primary_head,secondary_head,scope):
    ledger._tag(scope)
    for x in (primary_genesis,secondary_genesis,primary_head,secondary_head):
        cas.digest(x)
    if primary_genesis != secondary_genesis:
        raise DetachedHistoryConflict('different genesis enrollment cannot form one history fork')


def _replay(branch,scope,genesis,head):
    """Restore into a *memory-only* database and reuse the full trusted auditor."""
    if type(branch) is not dict or set(branch)!=BRANCH_FIELDS:
        raise DetachedHistoryConflict('incomplete detached history fields')
    events=branch['events']
    enrolled=branch['enrollment']
    if (type(events) is not list or len(events)>ledger.MAX_EVENTS
            or type(enrolled) is not dict or set(enrolled)!=set(ledger.ROLES)):
        raise DetachedHistoryConflict('invalid bounded event history or enrollment')
    if ledger.genesis_digest(scope,enrolled)!=genesis:
        raise DetachedHistoryConflict('detached enrollment not externally trusted')
    rows=[]
    for values in events:
        if (type(values) is not list or len(values)!=len(ledger.FIELDS)
                or type(values[0]) is not int
                or type(values[4]) is not int
                or any(type(item) is not str for index,item in enumerate(values)
                       if index not in (0,4))):
            raise DetachedHistoryConflict('invalid event row type or fields')
        rows.append(tuple(values))
    with closing(sqlite3.connect(':memory:')) as con:
        con.execute('PRAGMA user_version='+str(ledger.VERSION))
        con.execute('CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1),'
                    'schema TEXT NOT NULL,scope TEXT NOT NULL,genesis_sha256 TEXT NOT NULL)')
        con.execute('CREATE TABLE enrollment (role TEXT PRIMARY KEY,'
                    'operator_id TEXT NOT NULL,storage_id TEXT NOT NULL,'
                    'public_pin TEXT NOT NULL,initial_previous_sha256 TEXT NOT NULL)')
        con.execute('CREATE TABLE events (event_id INTEGER PRIMARY KEY,kind TEXT NOT NULL,'
                    'role TEXT NOT NULL,nonce TEXT NOT NULL,sequence INTEGER NOT NULL,'
                    'prior_receipt_sha256 TEXT NOT NULL,archive_sha256 TEXT NOT NULL,'
                    'evidence_sha256 TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,'
                    'previous_event_sha256 TEXT NOT NULL,event_sha256 TEXT NOT NULL)')
        con.execute('INSERT INTO meta VALUES (1,?,?,?)',(ledger.SCHEMA,scope,genesis))
        for role in ledger.ROLES:
            record=enrolled[role]
            con.execute('INSERT INTO enrollment VALUES (?,?,?,?,?)',
                (role,record['operator_id'],record['storage_id'],record['public_pin'],
                 record['initial_previous_sha256']))
        con.executemany('INSERT INTO events VALUES ('+
                        ','.join('?' for _ in ledger.FIELDS)+')',rows)
        result=ledger._audit(con)
    if (result['scope']!=scope or result['head']!=head
            or result['count']!=len(rows) or result['enrollment']!=enrolled):
        raise DetachedHistoryConflict('detached archive changed its trusted head')
    return result,tuple(rows)


def _verify_payload(data,*,scope,primary_genesis,secondary_genesis,
                    primary_head,secondary_head):
    _args_pins(primary_genesis,secondary_genesis,primary_head,secondary_head,scope)
    if (type(data) is not dict or set(data)!=FIELDS or data['schema']!=SCHEMA
            or data['scope']!=scope
            or data['primary_genesis_sha256']!=primary_genesis
            or data['secondary_genesis_sha256']!=secondary_genesis
            or data['primary_head_sha256']!=primary_head
            or data['secondary_head_sha256']!=secondary_head):
        raise DetachedHistoryConflict('detached evidence does not bind exact enrolled pins')
    first,rows_a=_replay(data['primary'],scope,primary_genesis,primary_head)
    second,rows_b=_replay(data['secondary'],scope,secondary_genesis,secondary_head)
    if first['enrollment']!=second['enrollment']:
        raise DetachedHistoryConflict('detached operator enrollments disagree')
    if rows_a==rows_b:
        raise DetachedHistoryConflict('identical histories do not establish divergence')
    kind,common,duplicate=cross._diagnose({'events':rows_a},{'events':rows_b})
    return {'kind':kind,'common':common,'duplicate':duplicate,
            'first_events':first['count'],'second_events':second['count']}


def _private_read(path):
    """Read one private regular inode with exact file-size/inode recheck."""
    path=private._secure_parent(path)
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        current=path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1
                or before.st_uid!=os.getuid() or before.st_mode&0o077
                or (before.st_dev,before.st_ino)!=(current.st_dev,current.st_ino)
                or before.st_size<1 or before.st_size>MAX_BYTES):
            raise DetachedHistoryConflict('unsafe bounded private archive inode')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw=stream.read(MAX_BYTES+1)
        after=os.fstat(fd)
        current=path.lstat()
        if (len(raw)!=before.st_size or before.st_size!=after.st_size
                or (after.st_dev,after.st_ino)!=(current.st_dev,current.st_ino)):
            raise DetachedHistoryConflict('archive inode or size changed during readback')
        return raw
    finally:
        os.close(fd)


def inspect(path,*,external_archive_pin,expected_scope,
            external_primary_genesis,external_secondary_genesis,
            external_primary_head,external_secondary_head):
    cas.digest(external_archive_pin)
    raw=_private_read(path)
    archive_pin=hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(archive_pin,external_archive_pin):
        raise DetachedHistoryConflict('independent archive bytes SHA-256 mismatch')
    try:
        obj=json.loads(raw,object_pairs_hook=cas._unique_json_fields,
                       parse_constant=cas._reject_json_constant)
    except (ValueError,UnicodeError) as exc:
        raise DetachedHistoryConflict('invalid unique-field JSON') from exc
    if raw!=_canonical(obj):
        raise DetachedHistoryConflict('noncanonical evidence JSON')
    reviewed=_verify_payload(obj,scope=expected_scope,
        primary_genesis=external_primary_genesis,
        secondary_genesis=external_secondary_genesis,
        primary_head=external_primary_head,
        secondary_head=external_secondary_head)
    return _report(archive_pin,reviewed,created=False)


def _report(sha,reviewed,*,created):
    return {
        'schema':REPORT_SCHEMA,'archive_sha256':sha,
        'conflict_class':reviewed['kind'],
        'common_verified_event_count':reviewed['common'],
        'cross_registry_duplicate_nonce_with_different_claims_detected':
            reviewed['duplicate'],
        'primary_verified_events':reviewed['first_events'],
        'secondary_verified_events':reviewed['second_events'],
        'detached_full_nonce_histories_replayed':True,
        'archive_exclusive_no_replace_creation_verified':created,
        'independently_stored_archive_pin_proved':False,
        'independent_offhost_evidence_custody_proved':False,
        'true_global_nonce_cas_consensus_proved':False,
        'either_signed_receipt_was_physically_stored_proved':False,
        'automatic_ledger_merge_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,'native_switch_game_build_verified':False,
    }


def create(path,primary,secondary,*,expected_scope,
           external_primary_genesis,external_secondary_genesis,
           external_primary_head,external_secondary_head):
    """Two source audit rounds before exclusive private evidence creation."""
    _args_pins(external_primary_genesis,external_secondary_genesis,
               external_primary_head,external_secondary_head,expected_scope)
    previous=None
    for _ in range(2):
        identities=cross._two_identities(primary,secondary)
        a=cross._read_once(primary,expected_scope=expected_scope,
            expected_genesis=external_primary_genesis,
            expected_head=external_primary_head)
        b=cross._read_once(secondary,expected_scope=expected_scope,
            expected_genesis=external_secondary_genesis,
            expected_head=external_secondary_head)
        if cross._two_identities(primary,secondary)!=identities:
            raise DetachedHistoryConflict('source inode changed during evidence collection')
        current=(a,b)
        if previous is not None and current!=previous:
            raise DetachedHistoryConflict('source histories changed between collection rounds')
        previous=current
    data={
        'schema':SCHEMA,'scope':expected_scope,
        'primary_genesis_sha256':external_primary_genesis,
        'secondary_genesis_sha256':external_secondary_genesis,
        'primary_head_sha256':external_primary_head,
        'secondary_head_sha256':external_secondary_head,
        'primary':{'enrollment':a['enrollment'],
                   'events':[list(event) for event in a['events']]},
        'secondary':{'enrollment':b['enrollment'],
                     'events':[list(event) for event in b['events']]},
    }
    reviewed=_verify_payload(data,scope=expected_scope,
        primary_genesis=external_primary_genesis,
        secondary_genesis=external_secondary_genesis,
        primary_head=external_primary_head,
        secondary_head=external_secondary_head)
    raw=_canonical(data)
    if not 0<len(raw)<=MAX_BYTES:
        raise DetachedHistoryConflict('detached evidence exceeds archive cap')
    archive_pin=hashlib.sha256(raw).hexdigest()
    private._write_exclusive(path,raw)
    result=inspect(path,external_archive_pin=archive_pin,
        expected_scope=expected_scope,
        external_primary_genesis=external_primary_genesis,
        external_secondary_genesis=external_secondary_genesis,
        external_primary_head=external_primary_head,
        external_secondary_head=external_secondary_head)
    result['archive_exclusive_no_replace_creation_verified']=True
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('create','inspect'))
    p.add_argument('archive',type=Path)
    p.add_argument('--primary-registry',type=Path)
    p.add_argument('--secondary-registry',type=Path)
    p.add_argument('--archive-pin')
    p.add_argument('--scope',required=True)
    for label in ('primary','secondary'):
        p.add_argument('--'+label+'-genesis-pin',required=True)
        p.add_argument('--'+label+'-head-pin',required=True)
    a=p.parse_args(argv)
    out={'schema':REPORT_SCHEMA,'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False,'automatic_cas_retry_authorized':False,
         'automatic_ledger_merge_authorized':False}
    trust=dict(expected_scope=a.scope,
        external_primary_genesis=a.primary_genesis_pin,
        external_secondary_genesis=a.secondary_genesis_pin,
        external_primary_head=a.primary_head_pin,
        external_secondary_head=a.secondary_head_pin)
    try:
        if a.action=='inspect':
            if a.archive_pin is None:
                raise DetachedHistoryConflict('independently retained archive pin required')
            result=inspect(a.archive,external_archive_pin=a.archive_pin,**trust)
        else:
            if a.primary_registry is None or a.secondary_registry is None:
                raise DetachedHistoryConflict('both source registries required for creation')
            if a.archive_pin is not None:
                raise DetachedHistoryConflict('created archive pin cannot be preclaimed')
            result=create(a.archive,a.primary_registry,a.secondary_registry,**trust)
        out.update(result)
        status=0
    except (DetachedHistoryConflict,cross.LedgerDivergence,
            ledger.NonceLedgerConflict,cas.CheckpointCASConflict,
            ValueError,TypeError,KeyError,IndexError,OSError,sqlite3.DatabaseError):
        out['detached_history_evidence_conflict']=True
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
