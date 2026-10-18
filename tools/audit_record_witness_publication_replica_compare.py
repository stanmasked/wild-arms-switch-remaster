"""Stage 263R: read-only, independently pinned publication-replica comparison.

Audit two distinct Stage 263Q SQLite ledgers with their *separately*
retained (count, head) pins plus one trusted historical floor (count,
head). Require the complete event histories to agree through the present,
not merely that their last SHA-256 values match. Refuse any local
conflict-freeze, stale replica, divergent fork or rollback below the floor.

These are two local SQLite snapshots, NOT remote authenticated replicas
or a global atomic snapshot. An attacker controlling both copies and all
independent pins (including the floor) can still replay an old history.
Never authorize release of an unresolved witness fence.
"""
import argparse
from contextlib import closing, ExitStack
import hashlib
import hmac
import json
from pathlib import Path
import os
import sqlite3

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_publication_intake import (
        _private_path, _connect, _audit, _expect, _sha, COLUMNS,
        GENESIS, PublicationConflict, MAX_RECORDS,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_publication_intake import (
        _private_path, _connect, _audit, _expect, _sha, COLUMNS,
        GENESIS, PublicationConflict, MAX_RECORDS,
    )

SCHEMA = 'wild-arms-ps1-publication-replica-comparison-v1'
DOMAIN = b'wild-arms-ps1-publication-replica-comparison-v1\x00'


class ReplicaConflict(ValueError):
    """Independently pinned replicas, trusted floor or histories disagree."""


def _floor(events, count, head):
    if type(count) is not int or not 0 <= count <= MAX_RECORDS:
        raise ReplicaConflict('invalid independently enrolled historical floor')
    _sha(head)
    if len(events) < count:
        raise ReplicaConflict('replica truncated below trusted historical floor')
    actual = GENESIS if count == 0 else events[count-1][-1]
    if not hmac.compare_digest(actual, head):
        raise ReplicaConflict('replica violates independent historical anchor')


def compare(path_a, count_a, head_a, path_b, count_b, head_b, *,
            floor_count, floor_head):
    """Read both complete local histories; never mutate either SQLite file."""
    _sha(head_a)
    _sha(head_b)
    _sha(floor_head)
    a = _private_path(path_a, exists=True)
    b = _private_path(path_b, exists=True)
    # Path spelling is not an identity guarantee: reject hard-linked aliases.
    sa, sb = os.stat(a,follow_symlinks=False),os.stat(b,follow_symlinks=False)
    if (sa.st_dev,sa.st_ino) == (sb.st_dev,sb.st_ino):
        raise ReplicaConflict('same SQLite object cannot be two archives')
    with ExitStack() as stack:
        conn_a = stack.enter_context(closing(_connect(a)))
        conn_b = stack.enter_context(closing(_connect(b)))
        conn_a.execute('BEGIN IMMEDIATE')
        try:
            conn_b.execute('BEGIN IMMEDIATE')
            try:
                count1,tip1,_,frozen1,scope1 = _audit(conn_a)
                count2,tip2,_,frozen2,scope2 = _audit(conn_b)
                _expect(count1,tip1,count_a,head_a)
                _expect(count2,tip2,count_b,head_b)
                sql = ('SELECT '+','.join(COLUMNS)+
                       ' FROM published_escrow_receipts ORDER BY sequence')
                events1=conn_a.execute(sql).fetchall()
                events2=conn_b.execute(sql).fetchall()
                if len(events1)!=count1 or len(events2)!=count2:
                    raise ReplicaConflict('publication event sequence changed')
                _floor(events1,floor_count,floor_head)
                _floor(events2,floor_count,floor_head)
                if events1 != events2:
                    shared=min(len(events1),len(events2))
                    if events1[:shared] == events2[:shared]:
                        raise ReplicaConflict('replica is missing newer publications')
                    raise ReplicaConflict('two independently pinned histories forked')
                if (count1 != count2 or tip1 != tip2 or scope1 != scope2):
                    raise ReplicaConflict('publication replica heads differ')
                if frozen1 or frozen2:
                    raise ReplicaConflict('published signed conflict freezes archive')
                commitment={
                    'schema':SCHEMA,
                    'event_count':count1,
                    'head_sha256':tip1,
                    'historical_floor_count':floor_count,
                    'historical_floor_sha256':floor_head,
                    'event_sha256s':[row[-1] for row in events1],
                }
                digest=hashlib.sha256(DOMAIN+_canonical(commitment)).hexdigest()
            finally:
                conn_b.rollback()
        finally:
            conn_a.rollback()
    return {
        'schema':SCHEMA,
        'compared_event_count':count1,
        'matching_head_sha256':tip1,
        'matching_event_sequence_sha256':digest,
        'all_events_match_in_two_supplied_replicas':True,
        'trusted_historical_floor_present_in_both':True,
        'conflicting_published_receipts_detected':False,
        'independent_replica_operators_authenticated':False,
        'physical_storage_independence_proved':False,
        'all_hidden_forks_or_archives_discovered':False,
        'global_latest_tip_freshness_proved':False,
        'rollback_if_all_pins_substituted_excluded':False,
        'cross_host_snapshot_atomicity_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_replica_a',type=Path)
    parser.add_argument('private_replica_b',type=Path)
    parser.add_argument('--a-count',type=int,required=True)
    parser.add_argument('--a-head',required=True)
    parser.add_argument('--b-count',type=int,required=True)
    parser.add_argument('--b-head',required=True)
    parser.add_argument('--floor-count',type=int,required=True)
    parser.add_argument('--floor-head',required=True)
    args=parser.parse_args(argv)
    result={'schema':SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        result.update(compare(
            args.private_replica_a,args.a_count,args.a_head,
            args.private_replica_b,args.b_count,args.b_head,
            floor_count=args.floor_count,floor_head=args.floor_head))
        code=0
    except (ReplicaConflict,PublicationConflict):
        result['replica_history_or_external_pin_conflict']=True
        code=1
    except (OSError,ValueError,TypeError,IndexError,sqlite3.Error):
        result['valid_input']=False
        code=2
    print(json.dumps(result,sort_keys=True))
    return code


if __name__=='__main__':
    raise SystemExit(main())
