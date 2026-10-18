"""Stage 264A: read-only reconciliation of an indeterminate Stage 263Z CAS.

Never replay an ambiguous write. Require the original externally trusted
previous generation/pair/event pins and the exact independently pinned
Stage 263Y report. Compare a recomputed candidate event to a complete
two-snapshot audit of the keeper. No writer/fence release is available.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import hmac

try:
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_replay_head_checkpoint import TAG
except ImportError:
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_replay_head_checkpoint import TAG

REPORT_SCHEMA = 'wild-arms-ps1-indeterminate-checkpoint-cas-reconciliation-v1'


class IndeterminateCASConflict(cas.CheckpointCASConflict):
    """The actual commit outcome cannot be safely classified."""


def _snapshot(path):
    """Audit one consistent SQLite read transaction, no implicit DB creation."""
    with closing(cas._connect(path,readonly=True)) as con:
        con.execute('BEGIN')
        try:
            state = cas._audit(con)
            rows = con.execute('SELECT generation, previous_event_sha256, '
                'previous_pair_sha256, pair_sha256, event_count, sequence_a, '
                'sequence_b, report_sha256, event_sha256 '
                'FROM checkpoint_events ORDER BY generation').fetchall()
            return tuple(state), [tuple(row) for row in rows]
        finally:
            con.rollback()


def reconcile(path, report_raw, *, independent_report_pin,
              scope, expected_generation, expected_pair_pin,
              expected_event_head):
    """Return a *read-only observation*, never authority to retry/retire."""
    item,report_pin = cas._report(report_raw,independent_report_pin)
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise IndeterminateCASConflict('invalid expected enrolled scope')
    cas.number(expected_generation,cas.MAX_COUNT,'expected generation')
    cas.digest(expected_pair_pin)
    cas.digest(expected_event_head)
    if (expected_generation >= cas.MAX_COUNT
            or item['previous_checkpoint_sha256'] != expected_pair_pin
            or item['proposed_new_checkpoint_sha256'] == expected_pair_pin):
        raise IndeterminateCASConflict('proposal not bound to expected old head')
    first_state, first_rows = _snapshot(path)
    second_state, second_rows = _snapshot(path)
    if first_state != second_state or first_rows != second_rows:
        raise IndeterminateCASConflict('checkpoint changed between observations')
    state, rows = second_state, second_rows
    if state[1] != scope:
        raise IndeterminateCASConflict('operator checkpoint scope mismatch')
    if expected_generation >= len(rows):
        raise IndeterminateCASConflict('trusted previous event missing from chain')
    prior = rows[expected_generation]
    if (prior[0] != expected_generation
            or not hmac.compare_digest(prior[3],expected_pair_pin)
            or not hmac.compare_digest(prior[8],expected_event_head)):
        raise IndeterminateCASConflict('trusted previous event not present')
    old_count, old_a, old_b = prior[4],prior[5],prior[6]
    new_count = item['new_event_count']
    new_a = item['source_a_new_sequence']
    new_b = item['source_b_new_sequence']
    new_pair = item['proposed_new_checkpoint_sha256']
    if (new_count <= old_count or new_a <= old_a or new_b <= old_b):
        raise IndeterminateCASConflict('proposal does not advance pinned source heads')
    new_gen = expected_generation+1
    new_event = cas.event_hash(new_gen,expected_event_head,
        expected_pair_pin,new_pair,new_count,new_a,new_b,report_pin)
    if state[0] == expected_generation:
        # Fully audited head exactly equals independent previous checkpoint.
        if (not hmac.compare_digest(state[2],expected_pair_pin)
                or not hmac.compare_digest(state[6],expected_event_head)):
            raise IndeterminateCASConflict('previous checkpoint no longer current')
        status='old_head_observed'
    elif state[0] >= new_gen:
        if new_gen >= len(rows):
            raise IndeterminateCASConflict('candidate generation disappeared')
        candidate = rows[new_gen]
        expected_row=(new_gen,expected_event_head,expected_pair_pin,
                      new_pair,new_count,new_a,new_b,report_pin,new_event)
        if candidate != expected_row:
            raise IndeterminateCASConflict('candidate event is absent or differs')
        if state[0] == new_gen:
            if (state[2] != new_pair or state[6] != new_event):
                raise IndeterminateCASConflict('candidate is not current')
            status='candidate_commit_observed'
        else:
            # Other commits have happened. Cannot use old/new as latest pins.
            status='candidate_superseded'
    else:
        raise IndeterminateCASConflict('unexpected external checkpoint generation')
    return {
        'schema':REPORT_SCHEMA,
        'attempt_observation':status,
        'audited_two_read_transactions_match':True,
        'expected_previous_event_in_verified_chain':True,
        'candidate_event_sha256':new_event,
        'candidate_pair_sha256':new_pair,
        'candidate_generation':new_gen,
        'observed_generation':state[0],
        'observed_event_head_sha256':state[6],
        'source_report_sha256':report_pin,
        'automatic_retry_authorized':False,
        'external_operator_acknowledgment_proved':False,
        'externally_retained_latest_pin_proved':False,
        'physical_durability_proved':False,
        'global_latest_head_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('database',type=Path)
    p.add_argument('--report-file',type=Path,required=True)
    p.add_argument('--independent-report-pin',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--expected-generation',type=int,required=True)
    p.add_argument('--expected-pair-pin',required=True)
    p.add_argument('--expected-event-head',required=True)
    a=p.parse_args(argv)
    output={'schema':REPORT_SCHEMA,'automatic_retry_authorized':False,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        result=reconcile(a.database,
            _read_limited(_private_regular_file(a.report_file),cas.MAX_REPORT),
            independent_report_pin=a.independent_report_pin,
            scope=a.scope,expected_generation=a.expected_generation,
            expected_pair_pin=a.expected_pair_pin,
            expected_event_head=a.expected_event_head)
        output.update(result)
        status=0
    except (IndeterminateCASConflict,cas.CheckpointCASConflict,
            sqlite3.DatabaseError,OSError,ValueError,KeyError,
            IndexError,TypeError):
        output['indeterminate_cas_conflict']=True
        status=1
    print(json.dumps(output,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
