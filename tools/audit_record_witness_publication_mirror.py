"""Stage 263R: compare independently pinned local publication-intake replicas.

Read two private SQLite journals with separate exact (count, head) pins.
Verify each full event chain, then compare event commitments by sequence.
A prefix replica is distinguishable from a divergent fork, but is NEVER
considered an up-to-date, accepted mirror. No copying, repair or unlock.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_witness_publication_intake import (
        _private_path, _connect, _audit, _expect, COLUMNS,
        REPORT_SCHEMA as INTAKE_REPORT,
    )
except ImportError:
    from audit_record_witness_publication_intake import (
        _private_path, _connect, _audit, _expect, COLUMNS,
        REPORT_SCHEMA as INTAKE_REPORT,
    )

SCHEMA = 'wild-arms-ps1-publication-mirror-comparison-v1'
MAX_ROWS = 96


class MirrorConflict(ValueError):
    """Different, incomplete or otherwise untrusted journal replicas."""


def _snapshot(path, count, head):
    path = _private_path(path, exists=True)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            observed_count, observed_head, _, frozen, scope = _audit(con)
            _expect(observed_count, observed_head, count, head)
            events = con.execute(
                'SELECT '+','.join(COLUMNS)+' FROM published_escrow_receipts '
                'ORDER BY sequence').fetchall()
            if len(events) != observed_count or len(events) > MAX_ROWS:
                raise MirrorConflict('incomplete bounded mirror snapshot')
            events = tuple(tuple(row) for row in events)
        finally:
            con.rollback()
    return events, frozen, scope


def compare(a_path, a_count, a_head, b_path, b_count, b_head):
    """Fail closed for divergence or stale replicas; no repair side effects."""
    if Path(a_path).resolve() == Path(b_path).resolve():
        raise MirrorConflict('two purported independent copies alias same file')
    a, frozen_a, scope_a = _snapshot(a_path, a_count, a_head)
    b, frozen_b, scope_b = _snapshot(b_path, b_count, b_head)
    common = min(len(a), len(b))
    prefix_equal = a[:common] == b[:common]
    if not prefix_equal:
        raise MirrorConflict('conflicting event commitments across replicas')
    if len(a) != len(b):
        raise MirrorConflict('one publication archive is a stale prefix')
    if a != b or frozen_a != frozen_b or scope_a != scope_b:
        raise MirrorConflict('publication mirrors disagree')
    return {
        'schema': SCHEMA,
        'both_independently_pinned_chains_valid': True,
        'identical_full_event_histories': True,
        'matching_conflict_freeze_state': True,
        'event_count': len(a),
        'intake_frozen_by_conflict': frozen_a,
        'separate_physical_storage_proved': False,
        'externally_pinned_heads_are_latest_proved': False,
        'hidden_third_archive_excluded': False,
        'historical_rollback_with_old_pins_excluded': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for tag in ('a','b'):
        p.add_argument(tag+'_private_intake',type=Path)
        p.add_argument('--'+tag+'-count',required=True,type=int)
        p.add_argument('--'+tag+'-head',required=True)
    args=p.parse_args(argv)
    output={'schema':SCHEMA,'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        output.update(compare(args.a_private_intake,args.a_count,args.a_head,
                              args.b_private_intake,args.b_count,args.b_head))
        status=0
    except (MirrorConflict,ValueError):
        output['mirror_divergence_or_staleness']=True
        status=1
    except (OSError,sqlite3.Error,TypeError,KeyError):
        output['valid_input']=False
        status=2
    print(json.dumps(output,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
