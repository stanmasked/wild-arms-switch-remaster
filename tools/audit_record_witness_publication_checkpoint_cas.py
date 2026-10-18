"""Stage 263Z: reference external-operator checkpoint CAS ledger (NOT production).

Requires an independently retained initial-state enrollment pin and, on every
operation, an out-of-band current generation, signed-pair pin and event-head
SHA-256. A SQLite BEGIN IMMEDIATE transaction verifies the entire append-only
chain before atomically replacing the singleton head and adding one event.
A new connection rereads the committed head. This is a reference local store;
its independence, access control and durability are NOT attested.
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
from urllib.parse import quote

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_replay_head_checkpoint import HEX64, TAG
    from .audit_record_witness_publication_live_source import MAX_COUNT, MAX_SEQUENCE
    from .audit_record_witness_publication_two_source import REPORT_SCHEMA as Y_SCHEMA
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_replay_head_checkpoint import HEX64, TAG
    from audit_record_witness_publication_live_source import MAX_COUNT, MAX_SEQUENCE
    from audit_record_witness_publication_two_source import REPORT_SCHEMA as Y_SCHEMA

SCHEMA = 'wild-arms-ps1-independent-checkpoint-cas-v1'
REPORT_SCHEMA = 'wild-arms-ps1-independent-checkpoint-cas-report-v1'
DOMAIN = b'wild-arms-ps1-independent-checkpoint-cas-event-v1\x00'
ENROLL_DOMAIN = b'wild-arms-ps1-independent-checkpoint-cas-enrollment-v1\x00'
ZERO = '0' * 64
USER_VERSION = 263
MAX_REPORT = 4096
FIELDS = {
    'schema','two_old_ed25519_authority_claims_verified',
    'old_pair_matches_independently_supplied_checkpoint',
    'two_distinct_authority_keys_and_dns_hosts_checked',
    'two_new_challenge_bound_ed25519_claims_verified',
    'each_authority_sequence_strictly_advanced',
    'new_event_count_strictly_advanced',
    'both_new_claims_match_expected_stage_263w_tuple',
    'previous_checkpoint_sha256','proposed_new_checkpoint_sha256',
    'new_event_count','new_head_sha256','source_a_new_sequence',
    'source_b_new_sequence','external_store_commit_or_readback_proved',
    'physical_or_administrative_independence_proved',
    'global_latest_head_proved','compromised_both_sources_rollback_excluded',
    'full_stage_263v_transition_rechecked_here',
    'witness_fence_retirement_authorized','witness_fence_retired',
    'native_switch_game_build_verified',
}
TRUE_FIELDS = (
    'two_old_ed25519_authority_claims_verified',
    'old_pair_matches_independently_supplied_checkpoint',
    'two_distinct_authority_keys_and_dns_hosts_checked',
    'two_new_challenge_bound_ed25519_claims_verified',
    'each_authority_sequence_strictly_advanced',
    'new_event_count_strictly_advanced',
    'both_new_claims_match_expected_stage_263w_tuple',
)
FALSE_FIELDS = (
    'external_store_commit_or_readback_proved',
    'physical_or_administrative_independence_proved',
    'global_latest_head_proved','compromised_both_sources_rollback_excluded',
    'full_stage_263v_transition_rechecked_here',
    'witness_fence_retirement_authorized','witness_fence_retired',
    'native_switch_game_build_verified',
)


class CheckpointCASConflict(ValueError):
    """Ledger, external pin, or conditional advancement failed closed."""


def digest(value):
    if type(value) is not str or not HEX64.fullmatch(value):
        raise CheckpointCASConflict('invalid independently retained SHA-256')
    return value


def number(value, maximum, label):
    if type(value) is not int or not 0 <= value <= maximum:
        raise CheckpointCASConflict('invalid nonnegative ' + label)
    return value


def enrollment_digest(scope, initial_pin, count, seq_a, seq_b):
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise CheckpointCASConflict('invalid external store scope')
    digest(initial_pin)
    number(count, MAX_COUNT, 'event count')
    number(seq_a, MAX_SEQUENCE, 'authority A sequence')
    number(seq_b, MAX_SEQUENCE, 'authority B sequence')
    return hashlib.sha256(ENROLL_DOMAIN + _canonical({
        'schema':SCHEMA,'scope':scope,'initial_pin_sha256':initial_pin,
        'initial_event_count':count,'initial_sequence_a':seq_a,
        'initial_sequence_b':seq_b,
    })).hexdigest()


def event_hash(generation, previous_event, previous_pin, pin,
               count, seq_a, seq_b, report_pin):
    item = {
        'schema':SCHEMA, 'generation':generation,
        'previous_event_sha256':previous_event,
        'previous_pair_sha256':previous_pin, 'pair_sha256':pin,
        'event_count':count, 'sequence_a':seq_a, 'sequence_b':seq_b,
        'report_sha256':report_pin,
    }
    return hashlib.sha256(DOMAIN+_canonical(item)).hexdigest()


def _require_file(path):
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        info = os.fstat(fd)
        current = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_dev != current.st_dev
                or info.st_ino != current.st_ino
                or stat.S_ISLNK(current.st_mode)
                or info.st_mode & 0o077):
            raise CheckpointCASConflict('unsafe external checkpoint database identity')
        return path, (info.st_dev, info.st_ino)
    except OSError as exc:
        raise CheckpointCASConflict('missing or inaccessible checkpoint database') from exc
    finally:
        if 'fd' in locals():
            os.close(fd)


def _connect(path, *, readonly=False):
    path, identity = _require_file(path)
    # mode=rw never silently replaces a missing/deleted local database.
    uri='file:'+quote(str(path.absolute()),safe='/')+'?mode='+('ro' if readonly else 'rw')
    con=sqlite3.connect(uri,uri=True,isolation_level=None,timeout=2.0)
    try:
        current = os.lstat(path)
        if (current.st_dev,current.st_ino) != identity:
            raise CheckpointCASConflict('database inode changed during open')
        con.execute('PRAGMA busy_timeout=2000')
        con.execute('PRAGMA trusted_schema=OFF')
        if not readonly:
            con.execute('PRAGMA synchronous=FULL')
            con.execute('PRAGMA journal_mode=DELETE')
        return con
    except BaseException:
        con.close()
        raise


def _schema(con):
    version=con.execute('PRAGMA user_version').fetchone()[0]
    if version != USER_VERSION:
        raise CheckpointCASConflict('unexpected external registry version')
    tables=con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('checkpoint_state','checkpoint_events')"
    ).fetchall()
    if {x[0] for x in tables} != {'checkpoint_state','checkpoint_events'}:
        raise CheckpointCASConflict('missing sealed checkpoint tables')


def _audit(con):
    _schema(con)
    if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise CheckpointCASConflict('checkpoint database corruption')
    rows=con.execute('SELECT generation,previous_event_sha256,'
        'previous_pair_sha256,pair_sha256,event_count,sequence_a,sequence_b,'
        'report_sha256,event_sha256 FROM checkpoint_events '
        'ORDER BY generation').fetchall()
    if not 1 <= len(rows) <= MAX_COUNT + 1:
        raise CheckpointCASConflict('invalid bounded checkpoint history')
    previous_event=ZERO
    for index,row in enumerate(rows):
        gen, prior_event, prior_pin, pin, count, seq_a, seq_b, report_pin, chain = row
        number(gen, MAX_COUNT, 'generation')
        number(count, MAX_COUNT, 'count')
        number(seq_a, MAX_SEQUENCE, 'sequence A')
        number(seq_b, MAX_SEQUENCE, 'sequence B')
        for item in (prior_event,prior_pin,pin,report_pin,chain):
            digest(item)
        if gen != index or prior_event != previous_event:
            raise CheckpointCASConflict('truncated or reordered checkpoint chain')
        if index == 0:
            if prior_pin != ZERO or report_pin != ZERO:
                raise CheckpointCASConflict('invalid checkpoint genesis event')
        else:
            last=rows[index-1]
            if (prior_pin != last[3] or pin == prior_pin
                    or count <= last[4] or seq_a <= last[5] or seq_b <= last[6]):
                raise CheckpointCASConflict('invalid checkpoint advancement chain')
        candidate=event_hash(gen,prior_event,prior_pin,pin,count,seq_a,seq_b,report_pin)
        if not hmac.compare_digest(chain,candidate):
            raise CheckpointCASConflict('modified checkpoint event')
        previous_event=candidate
    state=con.execute('SELECT generation,scope,pair_sha256,event_count,'
        'sequence_a,sequence_b,event_head_sha256 FROM checkpoint_state WHERE id=1').fetchone()
    if (state is None or con.execute('SELECT COUNT(*) FROM checkpoint_state').fetchone()[0] != 1
            or type(state[1]) is not str or not TAG.fullmatch(state[1])):
        raise CheckpointCASConflict('invalid checkpoint state')
    tail=rows[-1]
    if tuple(state[i] for i in (0,2,3,4,5,6)) != (
            tail[0],tail[3],tail[4],tail[5],tail[6],tail[8]):
        raise CheckpointCASConflict('checkpoint state differs from journal head')
    return state


def init(path, *, scope, initial_pin, count, seq_a, seq_b, external_enrollment_pin):
    expected=enrollment_digest(scope,initial_pin,count,seq_a,seq_b)
    if not hmac.compare_digest(digest(external_enrollment_pin),expected):
        raise CheckpointCASConflict('external enrollment pin differs')
    path=Path(path)
    fd=None
    try:
        fd=os.open(path,os.O_CREAT | os.O_EXCL | os.O_WRONLY
                   | getattr(os,'O_NOFOLLOW',0),0o600)
        os.close(fd)
        fd=None
        with closing(_connect(path)) as con:
            con.execute('BEGIN IMMEDIATE')
            try:
                con.execute('CREATE TABLE checkpoint_state ('
                    'id INTEGER PRIMARY KEY CHECK(id=1),'
                    'generation INTEGER NOT NULL,scope TEXT NOT NULL,'
                    'pair_sha256 TEXT NOT NULL,event_count INTEGER NOT NULL,'
                    'sequence_a INTEGER NOT NULL,sequence_b INTEGER NOT NULL,'
                    'event_head_sha256 TEXT NOT NULL)')
                con.execute('CREATE TABLE checkpoint_events ('
                    'generation INTEGER PRIMARY KEY,previous_event_sha256 TEXT NOT NULL,'
                    'previous_pair_sha256 TEXT NOT NULL,pair_sha256 TEXT NOT NULL,'
                    'event_count INTEGER NOT NULL,sequence_a INTEGER NOT NULL,'
                    'sequence_b INTEGER NOT NULL,report_sha256 TEXT NOT NULL,'
                    'event_sha256 TEXT NOT NULL)')
                con.execute('PRAGMA user_version='+str(USER_VERSION))
                head=event_hash(0,ZERO,ZERO,initial_pin,count,seq_a,seq_b,ZERO)
                con.execute('INSERT INTO checkpoint_events VALUES (?,?,?,?,?,?,?,?,?)',
                    (0,ZERO,ZERO,initial_pin,count,seq_a,seq_b,ZERO,head))
                con.execute('INSERT INTO checkpoint_state VALUES (?,?,?,?,?,?,?,?)',
                    (1,0,scope,initial_pin,count,seq_a,seq_b,head))
                con.commit()
            except BaseException:
                con.rollback()
                raise
        return inspect(path, expected_generation=0,
                       expected_pair_pin=initial_pin,expected_event_head=head)
    except FileExistsError as exc:
        raise CheckpointCASConflict('external checkpoint store already exists') from exc
    finally:
        if fd is not None:
            os.close(fd)


def _assert_expected(state, *, expected_generation,expected_pair_pin,expected_event_head):
    number(expected_generation,MAX_COUNT,'expected generation')
    digest(expected_pair_pin)
    digest(expected_event_head)
    if (state[0] != expected_generation
            or not hmac.compare_digest(state[2],expected_pair_pin)
            or not hmac.compare_digest(state[6],expected_event_head)):
        raise CheckpointCASConflict('external expected checkpoint stale or rolled back')


def _unique_json_fields(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            raise CheckpointCASConflict('duplicate Stage 263Y JSON field')
        value[key]=item
    return value


def _reject_json_constant(value):
    raise CheckpointCASConflict('non-finite Stage 263Y JSON number')


def _report(raw, independent_report_pin):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REPORT:
        raise CheckpointCASConflict('invalid bounded Stage 263Y report')
    actual=hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual,digest(independent_report_pin)):
        raise CheckpointCASConflict('untrusted Stage 263Y report bytes')
    try:
        item=json.loads(raw,object_pairs_hook=_unique_json_fields,
                        parse_constant=_reject_json_constant)
    except (UnicodeError,ValueError) as exc:
        raise CheckpointCASConflict('invalid Stage 263Y report JSON') from exc
    if (type(item) is not dict or set(item) != FIELDS
            or item['schema'] != Y_SCHEMA
            or any(item[key] is not True for key in TRUE_FIELDS)
            or any(item[key] is not False for key in FALSE_FIELDS)):
        raise CheckpointCASConflict('unexpected or unsafe Stage 263Y report semantics')
    for key in ('previous_checkpoint_sha256','proposed_new_checkpoint_sha256',
                'new_head_sha256'):
        digest(item[key])
    number(item['new_event_count'],MAX_COUNT,'new event count')
    number(item['source_a_new_sequence'],MAX_SEQUENCE,'sequence A')
    number(item['source_b_new_sequence'],MAX_SEQUENCE,'sequence B')
    return item,actual


def inspect(path, *, expected_generation,expected_pair_pin,expected_event_head):
    with closing(_connect(path,readonly=True)) as con:
        con.execute('BEGIN')
        try:
            state=_audit(con)
            _assert_expected(state,expected_generation=expected_generation,
                             expected_pair_pin=expected_pair_pin,
                             expected_event_head=expected_event_head)
        finally:
            con.rollback()
    return {
        'schema':REPORT_SCHEMA,'readback_matching_externally_supplied_pin':True,
        'generation':state[0],'pair_sha256':state[2],
        'event_count':state[3],'source_a_sequence':state[4],
        'source_b_sequence':state[5],'event_head_sha256':state[6],
        'independent_operator_or_host_proved':False,
        'rollback_protection_without_external_pins_proved':False,
        'physical_durability_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def advance(path, report_raw, *, independent_report_pin,expected_generation,
            expected_pair_pin,expected_event_head):
    item,report_pin=_report(report_raw,independent_report_pin)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            state=_audit(con)
            _assert_expected(state,expected_generation=expected_generation,
                             expected_pair_pin=expected_pair_pin,
                             expected_event_head=expected_event_head)
            gen,scope,pin,count,seq_a,seq_b,head=state
            if (gen >= MAX_COUNT
                    or item['previous_checkpoint_sha256'] != pin
                    or item['proposed_new_checkpoint_sha256'] == pin
                    or item['new_event_count'] <= count
                    or item['source_a_new_sequence'] <= seq_a
                    or item['source_b_new_sequence'] <= seq_b):
                raise CheckpointCASConflict('proposal cannot strictly advance external pin')
            newgen=gen+1
            newpin=item['proposed_new_checkpoint_sha256']
            newcount=item['new_event_count']
            newa=item['source_a_new_sequence']
            newb=item['source_b_new_sequence']
            newhead=event_hash(newgen,head,pin,newpin,newcount,newa,newb,report_pin)
            con.execute('INSERT INTO checkpoint_events VALUES (?,?,?,?,?,?,?,?,?)',
                (newgen,head,pin,newpin,newcount,newa,newb,report_pin,newhead))
            con.execute('UPDATE checkpoint_state SET generation=?,pair_sha256=?,'
                'event_count=?,sequence_a=?,sequence_b=?,event_head_sha256=? '
                'WHERE id=1 AND generation=? AND pair_sha256=? AND event_head_sha256=?',
                (newgen,newpin,newcount,newa,newb,newhead,gen,pin,head))
            if con.execute('SELECT changes()').fetchone()[0] != 1:
                raise CheckpointCASConflict('atomic conditional state update lost race')
            con.commit()
        except BaseException:
            con.rollback()
            raise
    # Separate connection reads back the full committed chain. If it has
    # advanced again, fail closed but DO NOT pretend the first write vanished.
    readback=inspect(path,expected_generation=newgen,
                     expected_pair_pin=newpin,expected_event_head=newhead)
    readback.update({
        'atomic_sqlite_cas_and_separate_readback_verified':True,
        'report_sha256':report_pin,
        'previous_event_head_sha256':head,
    })
    return readback


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('init','inspect','advance'))
    p.add_argument('database',type=Path)
    p.add_argument('--scope')
    p.add_argument('--initial-pin')
    p.add_argument('--initial-count',type=int)
    p.add_argument('--initial-sequence-a',type=int)
    p.add_argument('--initial-sequence-b',type=int)
    p.add_argument('--external-enrollment-pin')
    p.add_argument('--expected-generation',type=int)
    p.add_argument('--expected-pair-pin')
    p.add_argument('--expected-event-head')
    p.add_argument('--report-file',type=Path)
    p.add_argument('--independent-report-pin')
    a=p.parse_args(argv)
    report={'schema':REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        if a.action=='init':
            result=init(a.database,scope=a.scope,initial_pin=a.initial_pin,
                        count=a.initial_count,seq_a=a.initial_sequence_a,
                        seq_b=a.initial_sequence_b,
                        external_enrollment_pin=a.external_enrollment_pin)
        elif a.action=='inspect':
            result=inspect(a.database,expected_generation=a.expected_generation,
                           expected_pair_pin=a.expected_pair_pin,
                           expected_event_head=a.expected_event_head)
        else:
            if a.report_file is None:
                raise CheckpointCASConflict('missing pinned Stage Y report')
            result=advance(a.database,
                _read_limited(_private_regular_file(a.report_file),MAX_REPORT),
                independent_report_pin=a.independent_report_pin,
                expected_generation=a.expected_generation,
                expected_pair_pin=a.expected_pair_pin,
                expected_event_head=a.expected_event_head)
        report.update(result)
        status=0
    except (CheckpointCASConflict,sqlite3.DatabaseError,ValueError,
            TypeError,KeyError,IndexError,OSError):
        report['external_checkpoint_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
