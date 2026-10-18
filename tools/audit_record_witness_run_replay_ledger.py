"""Stage 263L: independent, monotonic-*by-policy* signed-run replay journal.

Require a fresh, private SQLite journal; a verified Stage 263K eight-claim
bundle; and an externally pinned last (count, head) on every enrollment.
A single BEGIN IMMEDIATE transaction verifies the full hash chain, rejects
globally reused (observer key, run nonce) pairs and composite reuse, then
appends one eight-claim event. There is NO release, delete or reset command.

Important: SQLite is not append-only storage against a privileged writer.
A host administrator can restore an older database and present a rolled-back
external head. Persistent independent head escrow is OPERATOR-ENFORCED, not
attested by this utility. No OS execution/revocation or fence release proof.
"""
import argparse
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
    from .audit_record_witness_composite_evidence import SPECS
    from .audit_record_witness_report_provenance import (
        verify as verify_origins, CLAIM_SCHEMA, DOMAIN as CLAIM_DOMAIN,
        MAX_INDEX, MAX_SIGNED, MAX_TOOL_SOURCE, MAX_REPORT, MAX_BUNDLE,
        _digest,
    )
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_composite_evidence import SPECS
    from audit_record_witness_report_provenance import (
        verify as verify_origins, CLAIM_SCHEMA, DOMAIN as CLAIM_DOMAIN,
        MAX_INDEX, MAX_SIGNED, MAX_TOOL_SOURCE, MAX_REPORT, MAX_BUNDLE,
        _digest,
    )
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA = 'wild-arms-ps1-observer-run-replay-ledger-v1'
REPORT_SCHEMA = 'wild-arms-ps1-observer-run-replay-report-v1'
DOMAIN = b'wild-arms-ps1-observer-run-replay-ledger-v1\x00'
GENESIS = hashlib.sha256(DOMAIN + b'genesis').hexdigest()
MARKER = 0x52504C59  # RPLY, normal signed SQLite user_version
MAX_EVENTS = 10000
CREATE_SQL = ("""CREATE TABLE observer_replay_events (
    sequence INTEGER PRIMARY KEY,
    schema TEXT NOT NULL,
    previous_sha256 TEXT NOT NULL,
    composite_sha256 TEXT NOT NULL,
    source_index_sha256 TEXT NOT NULL,
    observer_key_sha256 TEXT NOT NULL,
    signed_runs_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL
)""")
COLUMNS = (
    'sequence','schema','previous_sha256','composite_sha256',
    'source_index_sha256','observer_key_sha256','signed_runs_json',
    'event_sha256',
)


class ReplayConflict(ValueError):
    """Fail closed on reuse, journal rollback, corrupt chain or missing pin."""


def _private_path(path, *, exists):
    path = Path(path)
    if not path.is_absolute() or path.name in ('', '.', '..'):
        raise ValueError('journal requires absolute private path')
    directory = path.parent.lstat()
    if (not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.getuid()
            or directory.st_mode & 0o077):
        raise ValueError('journal directory must be private')
    if exists:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ReplayConflict('journal object is not private regular file')
    return path


def _connect(path):
    # URI mode=rw must never silently reinitialize an absent ledger.
    uri = 'file:' + quote(str(path), safe='/') + '?mode=rw'
    con = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=8)
    con.execute('PRAGMA busy_timeout=8000')
    con.execute('PRAGMA synchronous=FULL')
    return con


def initialize(path):
    path = _private_path(path, exists=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    os.close(fd)
    try:
        con = _connect(path)
        try:
            con.execute('BEGIN IMMEDIATE')
            con.execute(CREATE_SQL)
            con.execute('PRAGMA user_version=' + str(MARKER))
            con.commit()
            _audit(con)
        finally:
            con.close()
        # Require separately retained genesis pin before first enrollment.
        return _status(0, GENESIS, initialized=True)
    except Exception:
        # Never turn a partial first-create crash into implicit reset.
        # Leave the file in place; independent recovery is required.
        raise


def _signed_rows(raw):
    try:
        rows = json.loads(raw)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ReplayConflict('malformed stored observer claim list') from exc
    if (type(rows) is not list or len(rows) != len(SPECS)
            or raw != _canonical(rows).decode('ascii').rstrip('\n')):
        raise ReplayConflict('noncanonical stored observer claim list')
    seen_names = set()
    seen_nonces = set()
    for entry in rows:
        if (type(entry) is not dict or set(entry) !=
                {'kind','run_nonce','signed_claim_sha256'}
                or entry['kind'] not in SPECS
                or entry['kind'] in seen_names
                or type(entry['run_nonce']) is not str
                or len(entry['run_nonce']) != 32
                or any(c not in '0123456789abcdef' for c in entry['run_nonce'])
                or entry['run_nonce'] in seen_nonces):
            raise ReplayConflict('duplicate or malformed observer run nonce')
        _digest(entry['signed_claim_sha256'])
        seen_names.add(entry['kind'])
        seen_nonces.add(entry['run_nonce'])
    if seen_names != set(SPECS):
        raise ReplayConflict('incomplete stored observer claims')
    if [entry['kind'] for entry in rows] != sorted(SPECS):
        raise ReplayConflict('unordered stored observer claims')
    return rows


def _audit(con):
    header = con.execute('PRAGMA user_version').fetchone()[0]
    if header != MARKER:
        raise ReplayConflict('replay ledger SQLite header changed')
    tables = con.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()
    if tables != [('observer_replay_events', CREATE_SQL)]:
        raise ReplayConflict('replay ledger schema differs')
    columns = tuple(x[1] for x in con.execute(
        'PRAGMA table_info(observer_replay_events)'))
    if columns != COLUMNS:
        raise ReplayConflict('replay ledger columns differ')
    entries = con.execute(
        'SELECT sequence,schema,previous_sha256,composite_sha256,'
        'source_index_sha256,observer_key_sha256,signed_runs_json,'
        'event_sha256 FROM observer_replay_events ORDER BY sequence').fetchall()
    if len(entries) > MAX_EVENTS:
        raise ReplayConflict('replay ledger exceeds audited bound')
    seen_composite = set()
    seen_claims = set()
    previous = GENESIS
    for n, row in enumerate(entries, 1):
        seq,schema,prev,composite,index,key,claims,event = row
        if (type(seq) is not int or seq != n or schema != SCHEMA
                or prev != previous or not all(
                    type(x) is str and len(x) == 64
                    and all(c in '0123456789abcdef' for c in x)
                    for x in (composite,index,key,event))
                or composite in seen_composite):
            raise ReplayConflict('replay ledger sequence or digest mismatch')
        parsed = _signed_rows(claims)
        for item in parsed:
            identity = (key, item['run_nonce'])
            if identity in seen_claims:
                raise ReplayConflict('reused signed observer run in ledger')
            seen_claims.add(identity)
        bound = dict(zip(COLUMNS[:-1],row[:-1]))
        actual = hashlib.sha256(DOMAIN + _canonical(bound)).hexdigest()
        if not hmac.compare_digest(actual,event):
            raise ReplayConflict('replay journal event hash invalid')
        seen_composite.add(composite)
        previous = event
    return len(entries), previous, seen_composite, seen_claims


def _status(count, head, *, initialized=False, enrolled=False):
    return {
        'schema': REPORT_SCHEMA,
        'ledger_event_count': count,
        'ledger_head_sha256': head,
        'fresh_ledger_created': initialized,
        'signed_runs_enrolled_once': enrolled,
        'independent_head_escrow_proved': False,
        'permanent_rollback_prevention_proved': False,
        'tool_execution_independently_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def inspect(path, expected_count, expected_head):
    """Read-only inspection, checked against the operator's external pin."""
    path = _private_path(path, exists=True)
    with _connect(path) as con:
        con.execute('BEGIN IMMEDIATE')
        count,head,_,_ = _audit(con)
        _check_expected(count,head,expected_count,expected_head)
        con.rollback()
    return _status(count,head)


def _check_expected(count, head, expected_count, expected_head):
    if (type(expected_count) is not int or expected_count < 0
            or expected_count > MAX_EVENTS
            or type(expected_head) is not str
            or len(expected_head) != 64
            or any(x not in '0123456789abcdef' for x in expected_head)
            or not hmac.compare_digest(head, expected_head)
            or count != expected_count):
        raise ReplayConflict('ledger differs from independently retained head')


def enroll(path, composite_raw, composite_pin, index_raw, index_pin,
           reports, sources, signed_runs, observer_public, observer_pin, *,
           observer_tag, expected_count, expected_head):
    """Single lock/transaction for all eight claims and chain append."""
    # No journal mutation happens before complete external claim verification.
    origin = verify_origins(
        composite_raw, composite_pin, index_raw, index_pin,
        reports, sources, signed_runs, observer_public, observer_pin,
        observer_tag=observer_tag)
    if origin['witness_fence_retirement_authorized'] is not False:
        raise ReplayConflict('unexpected upstream release authorization')
    claims = []
    for kind in sorted(SPECS):
        body = _signed(signed_runs[kind], CLAIM_SCHEMA, CLAIM_DOMAIN,
                       observer_pin, observer_public)
        claims.append({
            'kind': kind, 'run_nonce':body['run_nonce'],
            'signed_claim_sha256': hashlib.sha256(
                signed_runs[kind]).hexdigest(),
        })
    claims_json = _canonical(claims).decode('ascii').rstrip('\n')
    path = _private_path(path, exists=True)
    con = _connect(path)
    try:
        con.execute('BEGIN IMMEDIATE')
        count,head,composites,seen = _audit(con)
        _check_expected(count,head,expected_count,expected_head)
        if count >= MAX_EVENTS or composite_pin in composites or any(
                (observer_pin, entry['run_nonce']) in seen for entry in claims):
            raise ReplayConflict('observer nonce or composite already enrolled')
        event = {
            'sequence': count+1, 'schema': SCHEMA,
            'previous_sha256': head,
            'composite_sha256': composite_pin,
            'source_index_sha256': index_pin,
            'observer_key_sha256': observer_pin,
            'signed_runs_json': claims_json,
        }
        event_hash = hashlib.sha256(
            DOMAIN + _canonical(event)).hexdigest()
        con.execute(
            'INSERT INTO observer_replay_events VALUES (?,?,?,?,?,?,?,?)',
            (*event.values(),event_hash))
        new_count,new_head,_,_ = _audit(con)
        if new_count != count+1 or new_head != event_hash:
            raise ReplayConflict('replay journal append failed')
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return _status(new_count,new_head,enrolled=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='action', required=True)
    p = modes.add_parser('init')
    p.add_argument('private_journal',type=Path)
    for name in ('inspect','enroll'):
        p = modes.add_parser(name)
        p.add_argument('private_journal',type=Path)
        p.add_argument('--expected-count',type=int,required=True)
        p.add_argument('--expected-head',required=True)
        if name == 'enroll':
            p.add_argument('private_composite',type=Path)
            p.add_argument('composite_sha256')
            p.add_argument('private_source_index',type=Path)
            p.add_argument('source_index_sha256')
            p.add_argument('pinned_observer_public',type=Path)
            p.add_argument('observer_public_sha256')
            p.add_argument('--observer-tag',required=True)
            for kind in SPECS:
                for role in ('report','tool-source','signed-run'):
                    p.add_argument('--'+kind+'-'+role,type=Path,required=True)
    args = parser.parse_args(argv)
    result = {
        'schema':REPORT_SCHEMA,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
    }
    try:
        if args.action=='init':
            result.update(initialize(args.private_journal))
        elif args.action=='inspect':
            result.update(inspect(args.private_journal,
                                  args.expected_count,args.expected_head))
        else:
            def rd(p,limit):
                return _read_limited(_private_regular_file(p),limit)
            result.update(enroll(
                args.private_journal,
                rd(args.private_composite,MAX_BUNDLE),args.composite_sha256,
                rd(args.private_source_index,MAX_INDEX),args.source_index_sha256,
                {k:rd(getattr(args,k+'_report'),MAX_REPORT) for k in SPECS},
                {k:rd(getattr(args,k+'_tool_source'),MAX_TOOL_SOURCE)
                 for k in SPECS},
                {k:rd(getattr(args,k+'_signed_run'),MAX_SIGNED)
                 for k in SPECS},
                args.pinned_observer_public,args.observer_public_sha256,
                observer_tag=args.observer_tag,
                expected_count=args.expected_count,
                expected_head=args.expected_head))
        code = 0
    except ReplayConflict:
        result['replay_or_independent_head_conflict'] = True
        code = 1
    except (ValueError,TypeError,KeyError,IndexError,OSError,
            sqlite3.Error,UnicodeError):
        result['valid_input'] = False
        code = 2
    print(json.dumps(result,sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
