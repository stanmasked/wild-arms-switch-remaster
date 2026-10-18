"""Stage 264J: fail-closed, locally atomic pre-sign receipt nonce ledger.

The caller MUST independently retain the latest reported ledger head SHA-256.
Reserve is committed BEFORE Ed25519 signing; failure leaves a pending
reservation that cannot be retried or silently cancelled. Each operator's
sequence/previous signed receipt and every nonce across both roles are unique.
This is local SQLite, NOT a deployed off-host monotonic CAS or physical WORM.
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
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_publication_checkpoint_cas import (
        _connect, digest, number, MAX_SEQUENCE, ZERO,
    )
    from .audit_record_witness_publication_replica_receipts import (
        _body, _enrolled_pem, ReceiptConflict,
    )
    from .audit_record_witness_replay_head_checkpoint import TAG, HEX32
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from . import audit_record_witness_publication_replica_receipts as receipts
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_publication_checkpoint_cas import (
        _connect, digest, number, MAX_SEQUENCE, ZERO,
    )
    from audit_record_witness_publication_replica_receipts import (
        _body, _enrolled_pem, ReceiptConflict,
    )
    from audit_record_witness_replay_head_checkpoint import TAG, HEX32
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    import audit_record_witness_publication_replica_receipts as receipts

SCHEMA='wild-arms-ps1-replica-receipt-nonce-ledger-v1'
REPORT_SCHEMA='wild-arms-ps1-replica-receipt-nonce-ledger-report-v1'
DOMAIN=b'wild-arms-ps1-replica-receipt-nonce-ledger-v1\x00'
VERSION=1
MAX_EVENTS=4096
ROLES=('operator-a','operator-b')
FIELDS=('event_id','kind','role','nonce','sequence','prior_receipt_sha256',
        'archive_sha256','evidence_sha256','receipt_sha256',
        'previous_event_sha256','event_sha256')


class NonceLedgerConflict(ReceiptConflict):
    """Nonce is consumed, external head changed, or ledger audit failed."""


def _tag(value):
    if type(value) is not str or not TAG.fullmatch(value):
        raise NonceLedgerConflict('invalid enrolled scope or operator ID')
    return value


def _nonce(value):
    if type(value) is not str or not HEX32.fullmatch(value):
        raise NonceLedgerConflict('invalid strict 128-bit nonce')
    return value


def _parent(path):
    path=Path(path)
    info=path.parent.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise NonceLedgerConflict('nonce ledger parent must be private')
    return path


def genesis_digest(scope,enrollment):
    _tag(scope)
    if (type(enrollment) is not dict or set(enrollment) != set(ROLES)):
        raise NonceLedgerConflict('exactly two enrolled receipt operators required')
    for role,items in enrollment.items():
        if (type(items) is not dict or set(items) !=
                {'operator_id','storage_id','public_pin','initial_previous_sha256'}):
            raise NonceLedgerConflict('incomplete operator enrollment')
        _tag(items['operator_id'])
        _tag(items['storage_id'])
        digest(items['public_pin'])
        digest(items['initial_previous_sha256'])
    if (enrollment['operator-a']['operator_id'] ==
            enrollment['operator-b']['operator_id']
            or enrollment['operator-a']['storage_id'] ==
            enrollment['operator-b']['storage_id']
            or enrollment['operator-a']['public_pin'] ==
            enrollment['operator-b']['public_pin']):
        raise NonceLedgerConflict('operator identities or enrollment keys overlap')
    return hashlib.sha256(DOMAIN+_canonical({
        'schema':SCHEMA,'scope':scope,'enrollment':enrollment,
    })).hexdigest()


def _hash_event(event):
    return hashlib.sha256(DOMAIN+_canonical({
        'schema':SCHEMA,**{k:event[k] for k in FIELDS if k!='event_sha256'}
    })).hexdigest()


def init(path,*,scope,enrollment,independent_genesis_pin):
    """Create-only, never overwrite; initial enrollment is externally pinned."""
    expected=genesis_digest(scope,enrollment)
    if not hmac.compare_digest(digest(independent_genesis_pin),expected):
        raise NonceLedgerConflict('initial registry enrollment pin mismatch')
    path=_parent(path)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY
               |getattr(os,'O_NOFOLLOW',0),0o600)
    os.close(fd)
    # Do not erase uncertain partial initialization: manual investigation.
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute('CREATE TABLE meta('
                        'id INTEGER PRIMARY KEY CHECK(id=1),'
                        'schema TEXT NOT NULL,scope TEXT NOT NULL,'
                        'genesis_sha256 TEXT NOT NULL)')
            con.execute('CREATE TABLE enrollment('
                        'role TEXT PRIMARY KEY,operator_id TEXT NOT NULL,'
                        'storage_id TEXT NOT NULL,public_pin TEXT NOT NULL,'
                        'initial_previous_sha256 TEXT NOT NULL)')
            con.execute('CREATE TABLE events('
                        'event_id INTEGER PRIMARY KEY,kind TEXT NOT NULL,'
                        'role TEXT NOT NULL,nonce TEXT NOT NULL,'
                        'sequence INTEGER NOT NULL,prior_receipt_sha256 TEXT NOT NULL,'
                        'archive_sha256 TEXT NOT NULL,evidence_sha256 TEXT NOT NULL,'
                        'receipt_sha256 TEXT NOT NULL,previous_event_sha256 TEXT NOT NULL,'
                        'event_sha256 TEXT NOT NULL)')
            con.execute('PRAGMA user_version='+str(VERSION))
            con.execute('INSERT INTO meta VALUES(1,?,?,?)',(SCHEMA,scope,expected))
            for role in ROLES:
                e=enrollment[role]
                con.execute('INSERT INTO enrollment VALUES(?,?,?,?,?)',
                    (role,e['operator_id'],e['storage_id'],
                     e['public_pin'],e['initial_previous_sha256']))
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
    return {'schema':REPORT_SCHEMA,'genesis_sha256':expected,
            'latest_ledger_sha256':expected,'event_count':0,
            'external_genesis_pin_independently_retained_proved':False,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}


def _audit(con):
    if con.execute('PRAGMA user_version').fetchone()[0]!=VERSION:
        raise NonceLedgerConflict('nonce ledger version mismatch')
    if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':
        raise NonceLedgerConflict('nonce ledger SQLite integrity failed')
    names={r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if names!={'meta','enrollment','events'}:
        raise NonceLedgerConflict('unexpected nonce ledger tables')
    meta=con.execute('SELECT id,schema,scope,genesis_sha256 FROM meta').fetchall()
    if len(meta)!=1 or meta[0][0]!=1 or meta[0][1]!=SCHEMA:
        raise NonceLedgerConflict('invalid enrolled registry metadata')
    _,_,scope,genesis=meta[0]
    enrolled={}
    for role,operator,storage,pin,previous in con.execute(
            'SELECT role,operator_id,storage_id,public_pin,initial_previous_sha256'
            ' FROM enrollment').fetchall():
        if role in enrolled or role not in ROLES:
            raise NonceLedgerConflict('duplicate or unexpected operator enrollment')
        enrolled[role]={'operator_id':operator,'storage_id':storage,
                        'public_pin':pin,'initial_previous_sha256':previous}
    if genesis_digest(scope,enrolled)!=genesis:
        raise NonceLedgerConflict('enrollment altered after initialized')
    state={role:{'seq':0,'head':enrolled[role]['initial_previous_sha256'],
                 'pending':None} for role in ROLES}
    head=genesis
    nonces=set()
    events=con.execute('SELECT '+','.join(FIELDS)+
                       ' FROM events ORDER BY event_id').fetchall()
    if len(events)>MAX_EVENTS:
        raise NonceLedgerConflict('nonce history exceeds bounded audit')
    for index,values in enumerate(events,1):
        e=dict(zip(FIELDS,values))
        role=e['role']
        if role not in ROLES or e['event_id']!=index or e['kind'] not in ('reserve','complete'):
            raise NonceLedgerConflict('invalid event sequence')
        _nonce(e['nonce'])
        number(e['sequence'],MAX_SEQUENCE,'operator sequence')
        for field in ('prior_receipt_sha256','archive_sha256','evidence_sha256',
                      'receipt_sha256','previous_event_sha256','event_sha256'):
            digest(e[field])
        if e['previous_event_sha256']!=head or _hash_event(e)!=e['event_sha256']:
            raise NonceLedgerConflict('nonce hash chain changed')
        current=state[role]
        event_tuple=(e['nonce'],e['sequence'],e['prior_receipt_sha256'],
                     e['archive_sha256'],e['evidence_sha256'])
        if e['kind']=='reserve':
            if (e['receipt_sha256']!=ZERO or e['nonce'] in nonces
                    or current['pending'] is not None
                    or e['sequence'] != current['seq']+1
                    or e['prior_receipt_sha256'] != current['head']):
                raise NonceLedgerConflict('duplicate or nonmonotonic pre-sign reservation')
            nonces.add(e['nonce'])
            current['pending']=event_tuple
        else:
            if (current['pending']!=event_tuple
                    or e['receipt_sha256']==ZERO):
                raise NonceLedgerConflict('completion without exact pending reservation')
            current['seq']=e['sequence']
            current['head']=e['receipt_sha256']
            current['pending']=None
        head=e['event_sha256']
    return {'scope':scope,'enrollment':enrolled,'head':head,'count':len(events),
            'state':state}


def _append(con,base,kind,role,nonce,seq,previous,archive_pin,evidence_pin,receipt_pin):
    event={'event_id':base['count']+1,'kind':kind,'role':role,'nonce':nonce,
           'sequence':seq,'prior_receipt_sha256':previous,
           'archive_sha256':archive_pin,'evidence_sha256':evidence_pin,
           'receipt_sha256':receipt_pin,'previous_event_sha256':base['head']}
    if event['event_id']>MAX_EVENTS:
        raise NonceLedgerConflict('nonce ledger reached bounded event limit')
    event['event_sha256']=_hash_event(event)
    con.execute('INSERT INTO events VALUES ('+','.join('?' for _ in FIELDS)+')',
                tuple(event[f] for f in FIELDS))
    return event['event_sha256']


def snapshot(path,*,expected_ledger_head=None):
    """Strict read-only full hash-chain audit; return pending slots clearly."""
    _parent(path)
    with closing(_connect(path,readonly=True)) as con:
        con.execute('BEGIN')
        s=_audit(con)
        if (expected_ledger_head is not None and
                not hmac.compare_digest(digest(expected_ledger_head),s['head'])):
            raise NonceLedgerConflict('current ledger rolled back below external head')
        con.execute('COMMIT')
    return {
        'schema':REPORT_SCHEMA,'latest_ledger_sha256':s['head'],
        'scope':s['scope'],'event_count':s['count'],
        'pending_operator_roles':[role for role in ROLES
                                  if s['state'][role]['pending'] is not None],
        'completed_operator_sequences':{role:s['state'][role]['seq']
                                        for role in ROLES},
        'independent_latest_ledger_retention_proved':False,
        'physical_durability_proved':False,
        'witness_fence_retirement_authorized':False,'witness_fence_retired':False,
        'automatic_cas_retry_authorized':False,
    }


def _record(path,*,action,expected_head,scope,role,operator_id,storage_id,
            operator_public_pin,nonce,seq,previous,archive_pin,evidence_pin,
            receipt_pin=ZERO):
    _parent(path)
    for p in (expected_head,operator_public_pin,previous,archive_pin,
              evidence_pin,receipt_pin):
        digest(p)
    _nonce(nonce)
    if role not in ROLES:
        raise NonceLedgerConflict('invalid enrolled operator role')
    _tag(operator_id)
    _tag(storage_id)
    _tag(scope)
    number(seq,MAX_SEQUENCE,'receipt sequence')
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            base=_audit(con)
            if base['scope']!=scope or base['head']!=expected_head:
                raise NonceLedgerConflict('expected external ledger head mismatches')
            enrolled=base['enrollment'][role]
            if (enrolled['operator_id']!=operator_id
                    or enrolled['storage_id']!=storage_id
                    or enrolled['public_pin']!=operator_public_pin):
                raise NonceLedgerConflict('operator not enrolled to sign in this registry')
            state=base['state'][role]
            pending=(nonce,seq,previous,archive_pin,evidence_pin)
            if action=='reserve':
                if (state['pending'] is not None
                        or seq!=state['seq']+1 or previous!=state['head']
                        or receipt_pin!=ZERO
                        or con.execute('SELECT 1 FROM events'
                            ' WHERE kind=? AND nonce=? LIMIT 1',
                            ('reserve',nonce)).fetchone() is not None):
                    raise NonceLedgerConflict('nonce consumed or sequence has pending signature')
            elif action=='complete':
                if (state['pending']!=pending or receipt_pin==ZERO):
                    raise NonceLedgerConflict('unmatched receipt for consumed reservation')
            else:
                raise NonceLedgerConflict('invalid nonce operation')
            head=_append(con,base,action,role,nonce,seq,previous,
                         archive_pin,evidence_pin,receipt_pin)
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
    return head


def guarded_attest(path,registry_path,*,expected_registry_head,**kwargs):
    """Atomic pre-sign consume, then sign and append completion; no retry."""
    # Check public key pin without touching the ledger on invalid enrollment.
    _enrolled_pem(kwargs['receipt_public'],kwargs['receipt_public_pin'])
    expected_body=_body(kwargs['role'],kwargs['operator_id'],
        kwargs['storage_id'],kwargs['scope'],kwargs['audit_id'],kwargs['nonce'],
        kwargs['receipt_sequence'],kwargs['previous_receipt_sha256'],
        kwargs['independent_archive_pin'],kwargs['independent_evidence_pin'])
    fields=dict(scope=expected_body['checkpoint_scope'],
        role=expected_body['operator_role'],operator_id=expected_body['operator_id'],
        storage_id=expected_body['storage_id'],
        operator_public_pin=kwargs['receipt_public_pin'],
        nonce=expected_body['challenge_nonce'],
        seq=expected_body['receipt_sequence'],
        previous=expected_body['previous_receipt_sha256'],
        archive_pin=expected_body['archive_sha256'],
        evidence_pin=expected_body['canonical_evidence_sha256'])
    reserved=_record(registry_path,action='reserve',
                     expected_head=expected_registry_head,**fields)
    # If sign, readback or finalization fails, the ledger remains pending.
    # No rollback or automatic reuse of nonce is permitted.
    attested=receipts.attest(path,**kwargs)
    signed=_read_limited(_private_regular_file(kwargs['output']),receipts.MAX_RECEIPT)
    body=_signed(signed,receipts.SCHEMA,receipts.DOMAIN,
                 kwargs['receipt_public_pin'],kwargs['receipt_public'])
    if body!=expected_body:
        raise NonceLedgerConflict('signed output disagrees with reserved identity')
    actual=hashlib.sha256(signed).hexdigest()
    if actual!=attested['receipt_envelope_sha256']:
        raise NonceLedgerConflict('signed output changed before ledger completion')
    committed=_record(registry_path,action='complete',expected_head=reserved,
                      receipt_pin=actual,**fields)
    return {**attested,
            'nonce_consumed_before_receipt_signing':True,
            'nonce_ledger_completed_with_exact_signed_receipt':True,
            'latest_ledger_sha256':committed,
            'independently_retained_latest_ledger_proved':False,
            'offhost_monotonic_nonce_cas_proved':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('init','audit'))
    p.add_argument('registry',type=Path)
    p.add_argument('--scope')
    p.add_argument('--expected-genesis-pin')
    p.add_argument('--expected-ledger-head')
    for letter in ('a','b'):
        p.add_argument('--operator-'+letter+'-id')
        p.add_argument('--storage-'+letter+'-id')
        p.add_argument('--operator-'+letter+'-public',type=Path)
        p.add_argument('--operator-'+letter+'-pin')
        p.add_argument('--operator-'+letter+'-initial-previous-sha256')
    a=p.parse_args(argv)
    report={'schema':REPORT_SCHEMA,'automatic_cas_retry_authorized':False,
            'witness_fence_retirement_authorized':False,'witness_fence_retired':False}
    try:
        if a.action=='init':
            if a.scope is None or a.expected_genesis_pin is None:
                raise NonceLedgerConflict('missing trusted genesis enrollment')
            enrollment={}
            identities=[]
            for role,letter in (('operator-a','a'),('operator-b','b')):
                public=getattr(a,'operator_'+letter+'_public')
                pin=getattr(a,'operator_'+letter+'_pin')
                identities.append(_enrolled_pem(public,pin))
                enrollment[role]={
                    'operator_id':getattr(a,'operator_'+letter+'_id'),
                    'storage_id':getattr(a,'storage_'+letter+'_id'),
                    'public_pin':pin,
                    'initial_previous_sha256':getattr(
                        a,'operator_'+letter+'_initial_previous_sha256'),
                }
            if len(set(identities)) != 2:
                raise NonceLedgerConflict('two operator DER keys are identical')
            report.update(init(a.registry,scope=a.scope,enrollment=enrollment,
                               independent_genesis_pin=a.expected_genesis_pin))
        else:
            if a.expected_ledger_head is None:
                raise NonceLedgerConflict('missing independently retained current head')
            report.update(snapshot(a.registry,
                                   expected_ledger_head=a.expected_ledger_head))
        status=0
    except (NonceLedgerConflict,ReceiptConflict,ValueError,TypeError,
            KeyError,AttributeError,OSError,sqlite3.DatabaseError):
        report['nonce_ledger_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
