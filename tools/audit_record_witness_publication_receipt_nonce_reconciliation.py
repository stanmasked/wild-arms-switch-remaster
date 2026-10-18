"""Stage 264K: read-only two-ledger reconciliation under two external pins.

Checks two complete, locally separate Stage 264J nonce ledgers twice.
Classifies a full-prefix lag, a fork, and duplicate nonce reservation across
divergent histories. Returns success ONLY for identical enrolled chains.
Nothing here provisions independent operators, cross-host CAS or a latest-head
authority; external pins must genuinely come from distinct trusted sources.
"""
import argparse
from contextlib import closing
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat

try:
    from . import audit_record_witness_publication_receipt_nonce_ledger as ledger
    from . import audit_record_witness_publication_checkpoint_cas as cas
except ImportError:
    import audit_record_witness_publication_receipt_nonce_ledger as ledger
    import audit_record_witness_publication_checkpoint_cas as cas

SCHEMA='wild-arms-ps1-nonce-dual-ledger-reconciliation-v1'


class LedgerDivergence(ledger.NonceLedgerConflict):
    def __init__(self, reason, *, kind='untrusted',
                 common_events=None, duplicate_nonce_claims=False):
        super().__init__(reason)
        self.kind=kind
        self.common_events=common_events
        self.duplicate_nonce_claims=duplicate_nonce_claims


def _identity(path):
    """Different *private directory inodes* and private ordinary files."""
    path=ledger._parent(path)
    parent=path.parent.lstat()
    item=path.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid()
            or parent.st_mode&0o077 or not stat.S_ISREG(item.st_mode)
            or item.st_uid!=os.getuid() or item.st_mode&0o077
            or item.st_nlink!=1):
        raise LedgerDivergence('unsafe registry file or parent')
    return (parent.st_dev,parent.st_ino,item.st_dev,item.st_ino)


def _two_identities(a,b):
    left,right=_identity(a),_identity(b)
    if left[:2]==right[:2] or left[2:]==right[2:]:
        raise LedgerDivergence('two paths do not establish separate private files')
    return left,right


def _read_once(path,*,expected_scope,expected_genesis,expected_head):
    cas.digest(expected_genesis)
    cas.digest(expected_head)
    before=_identity(path)
    with closing(cas._connect(path,readonly=True)) as con:
        con.execute('BEGIN')
        report=ledger._audit(con)
        row=con.execute('SELECT genesis_sha256 FROM meta WHERE id=1').fetchone()
        events=con.execute('SELECT '+','.join(ledger.FIELDS)+
                           ' FROM events ORDER BY event_id').fetchall()
        con.execute('COMMIT')
    if _identity(path)!=before:
        raise LedgerDivergence('registry inode swapped during audit')
    if (report['scope'] != expected_scope
            or row is None or row[0] != expected_genesis
            or report['head'] != expected_head):
        raise LedgerDivergence('registered scope, enrollment or external head mismatches')
    if ledger.genesis_digest(report['scope'],report['enrollment'])!=expected_genesis:
        raise LedgerDivergence('signed enrollment genesis differs from external pin')
    return {'identity':before,'head':report['head'],
            'enrollment':report['enrollment'],'count':report['count'],
            'events':tuple(events),'scope':report['scope']}


def _diagnose(first,second):
    a,b=first['events'],second['events']
    common=0
    for x,y in zip(a,b):
        if x!=y:
            break
        common+=1
    if common==min(len(a),len(b)):
        kind='strict_prefix_lag'
    else:
        kind='forked_hash_chains'
    def _reserved(events):
        out={}
        for row in events:
            entry=dict(zip(ledger.FIELDS,row))
            if entry['kind']=='reserve':
                out[entry['nonce']]=(
                    entry['role'],entry['sequence'],
                    entry['prior_receipt_sha256'],
                    entry['archive_sha256'],entry['evidence_sha256'])
        return out
    left,right=_reserved(a),_reserved(b)
    collision=any(left[n]!=right[n] for n in left.keys() & right.keys())
    return kind,common,collision


def verify(primary,secondary, *,
           primary_head_pin,secondary_head_pin,
           primary_genesis_pin,secondary_genesis_pin,expected_scope):
    """Two rounds: audited, externally pinned ledgers must match byte-for-row.

    A different independently pinned later ledger is *diagnosed*, not merged
    or used to authorize signing. No input is modified.
    """
    ledger._tag(expected_scope)
    for x in (primary_head_pin,secondary_head_pin,
              primary_genesis_pin,secondary_genesis_pin):
        cas.digest(x)
    if not hmac.compare_digest(primary_genesis_pin,secondary_genesis_pin):
        raise LedgerDivergence('two enrolled ledgers have different genesis pins')
    old=None
    for _ in range(2):
        identities=_two_identities(primary,secondary)
        left=_read_once(primary,expected_scope=expected_scope,
                        expected_genesis=primary_genesis_pin,
                        expected_head=primary_head_pin)
        right=_read_once(secondary,expected_scope=expected_scope,
                         expected_genesis=secondary_genesis_pin,
                         expected_head=secondary_head_pin)
        if _two_identities(primary,secondary)!=identities:
            raise LedgerDivergence('registry identities changed during two-ledger audit')
        pair=(left,right)
        if old is not None and pair!=old:
            raise LedgerDivergence('registry changed between audit rounds')
        old=pair
    if left['enrollment']!=right['enrollment']:
        raise LedgerDivergence('operator enrollments disagree despite same genesis')
    if left['events'] != right['events']:
        kind,common,collision=_diagnose(left,right)
        raise LedgerDivergence('two fully audited ledgers disagree',
                               kind=kind,common_events=common,
                               duplicate_nonce_claims=collision)
    if left['head']!=right['head'] or left['count']!=right['count']:
        raise LedgerDivergence('history heads mismatch despite identical events')
    return {
        'schema':SCHEMA,
        'two_read_only_audit_rounds_completed':True,
        'two_distinct_local_private_directory_inodes_observed':True,
        'two_distinct_private_registry_file_inodes_observed':True,
        'two_external_current_head_sha256_constraints_met':True,
        'both_full_nonce_event_hash_chains_identical':True,
        'same_enrolled_operator_genesis_verified':True,
        'event_count':left['count'],
        'genesis_sha256':primary_genesis_pin,
        'latest_ledger_sha256':primary_head_pin,
        'offhost_admin_independence_proved':False,
        'independent_external_head_persistence_proved':False,
        'global_nonce_cas_consensus_proved':False,
        'registry_durability_proved':False,
        'automatic_ledger_merge_authorized':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('primary',type=Path)
    p.add_argument('secondary',type=Path)
    p.add_argument('--primary-head-pin',required=True)
    p.add_argument('--secondary-head-pin',required=True)
    p.add_argument('--primary-genesis-pin',required=True)
    p.add_argument('--secondary-genesis-pin',required=True)
    p.add_argument('--scope',required=True)
    a=p.parse_args(argv)
    out={'schema':SCHEMA,
         'automatic_ledger_merge_authorized':False,
         'automatic_cas_retry_authorized':False,
         'witness_fence_retirement_authorized':False,
         'witness_fence_retired':False}
    try:
        out.update(verify(a.primary,a.secondary,
            primary_head_pin=a.primary_head_pin,
            secondary_head_pin=a.secondary_head_pin,
            primary_genesis_pin=a.primary_genesis_pin,
            secondary_genesis_pin=a.secondary_genesis_pin,
            expected_scope=a.scope))
        status=0
    except LedgerDivergence as exc:
        out['nonce_ledger_reconciliation_conflict']=True
        out['conflict_class']=exc.kind
        if exc.common_events is not None:
            out['common_verified_event_count']=exc.common_events
            out['cross_registry_duplicate_nonce_with_different_claims_detected']=(
                exc.duplicate_nonce_claims)
        status=1
    except (ledger.NonceLedgerConflict,cas.CheckpointCASConflict,
            ValueError,TypeError,KeyError,IndexError,
            OSError,sqlite3.DatabaseError):
        out['nonce_ledger_reconciliation_conflict']=True
        out['conflict_class']='untrusted'
        status=1
    print(json.dumps(out,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
