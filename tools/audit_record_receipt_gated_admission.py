"""Opt-in receipt-gated one-at-a-time PS1 capture admission.

After each durable verifier issue/accept transaction, a pending checkpoint
digest is recorded in THE SAME SQLite transaction. No next operation can
run until a separately deposited checkpoint and matching latest custodian
receipt are acknowledged. Custody/authentication remain external concerns.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3

try:
    from .audit_record_atomic_verifier import (
        _connect, MIN_TTL_SECONDS, MAX_TTL_SECONDS,
    )
    from .audit_record_anchor_handoff import (
        _read_latest, _receipt, _canonical, _receipt_hash, MAX_RECEIPT_BYTES,
    )
    from .audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES,
        MAX_RECEIPT_BYTES as MAX_COLLECTOR_RECEIPT_BYTES,
    )
    from .audit_record_capture_stream_binding import (
        _read_limited, _parse, _digest, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_guarded_admission import _now
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _snapshot_from_connection, _validate_checkpoint,
    )
except ImportError:
    from audit_record_atomic_verifier import _connect, MIN_TTL_SECONDS, MAX_TTL_SECONDS
    from audit_record_anchor_handoff import (
        _read_latest, _receipt, _canonical, _receipt_hash, MAX_RECEIPT_BYTES,
    )
    from audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES,
        MAX_RECEIPT_BYTES as MAX_COLLECTOR_RECEIPT_BYTES,
    )
    from audit_record_capture_stream_binding import (
        _read_limited, _parse, _digest, _sha, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_guarded_admission import _now
    from audit_record_verifier_checkpoint import (
        _private_regular_file, _snapshot_from_connection, _validate_checkpoint,
    )

REPORT_SCHEMA = 'wild-arms-ps1-receipt-gated-admission-v1'
ISSUE_SCHEMA = 'wild-arms-ps1-receipt-gated-issue-v1'
GUARD_COLUMNS = frozenset({
    'slot', 'ack_sequence', 'ack_receipt_sha256',
    'pending_sequence', 'pending_checkpoint_sha256',
})


class PendingHandoff(ValueError):
    """Do not mutate verifier state until custodian confirms prior commit."""


class AnchorConflict(ValueError):
    """The offered custodian high-water record mismatches local state."""


def _latest_with_receipt(custodian_db, receipt_raw):
    """Check one local custody snapshot and a PRIVATE receipt for that snapshot."""
    if type(receipt_raw) is not bytes or not 0 < len(receipt_raw) <= MAX_RECEIPT_BYTES:
        raise ValueError('invalid bounded custodian receipt')
    receipt = _parse(receipt_raw)
    latest = _read_latest(custodian_db)
    if receipt != _receipt(latest[0], latest[1], latest[2]):
        raise AnchorConflict('stale or invalid custodian receipt')
    return latest


def _guard(con, *, create=False):
    if create:
        con.execute("""CREATE TABLE IF NOT EXISTS receipt_gate (
            slot INTEGER PRIMARY KEY CHECK (slot=1),
            ack_sequence INTEGER NOT NULL,
            ack_receipt_sha256 TEXT NOT NULL,
            pending_sequence INTEGER,
            pending_checkpoint_sha256 TEXT,
            CHECK ((pending_sequence IS NULL AND pending_checkpoint_sha256 IS NULL)
                OR (pending_sequence IS NOT NULL AND pending_checkpoint_sha256 IS NOT NULL))
        )""")
    else:
        if con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='receipt_gate'").fetchone() is None:
            raise ValueError('missing receipt-gated admission state')
    columns = {r[1] for r in con.execute('PRAGMA table_info("receipt_gate")')}
    if columns != GUARD_COLUMNS:
        raise ValueError('invalid receipt-gated admission schema')
    rows = con.execute(
        'SELECT slot,ack_sequence,ack_receipt_sha256,pending_sequence,'
        'pending_checkpoint_sha256 FROM receipt_gate').fetchall()
    if len(rows) != 1:
        raise ValueError('invalid receipt-gated admission row count')
    slot, seq, receipt_hash, pending_seq, pending_digest = rows[0]
    if (type(slot) is not int or slot != 1
            or type(seq) is not int or seq < 1):
        raise ValueError('invalid receipt-gated admission counters')
    _digest(receipt_hash)
    if pending_seq is not None:
        if type(pending_seq) is not int or pending_seq != seq + 1:
            raise ValueError('invalid pending receipt sequence')
        _digest(pending_digest)
    elif pending_digest is not None:
        raise ValueError('invalid pending receipt digest')
    return seq, receipt_hash, pending_seq, pending_digest


def _checkpoint_digest(con):
    return _sha(_canonical(_snapshot_from_connection(con)))


def _ready(con, latest):
    """Under BEGIN IMMEDIATE: must exactly equal last custodian checkpoint."""
    ack_seq, ack_hash, pending_seq, _ = _guard(con)
    if pending_seq is not None:
        raise PendingHandoff('previous verifier operation awaits custodian receipt')
    if (ack_seq != latest[0] or ack_hash != latest[3]
            or _checkpoint_digest(con) != latest[1]):
        raise AnchorConflict('custodian high-water checkpoint differs from verifier')
    return ack_seq


def bootstrap(verifier_db, custodian_db, receipt_raw):
    """Explicit one-time bootstrap only when verifier state equals custody."""
    latest = _latest_with_receipt(custodian_db, receipt_raw)
    with closing(_connect(verifier_db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            if _checkpoint_digest(con) != latest[1]:
                raise AnchorConflict('verifier not at custody bootstrap checkpoint')
            if con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='receipt_gate'").fetchone() is not None:
                raise ValueError('receipt-gated bootstrap already attempted')
            con.execute("""CREATE TABLE receipt_gate (
                slot INTEGER PRIMARY KEY CHECK (slot=1),
                ack_sequence INTEGER NOT NULL,
                ack_receipt_sha256 TEXT NOT NULL,
                pending_sequence INTEGER,
                pending_checkpoint_sha256 TEXT,
                CHECK ((pending_sequence IS NULL AND pending_checkpoint_sha256 IS NULL)
                    OR (pending_sequence IS NOT NULL AND pending_checkpoint_sha256 IS NOT NULL))
            )""")
            con.execute(
                'INSERT INTO receipt_gate(slot,ack_sequence,ack_receipt_sha256)'
                ' VALUES(1,?,?)', (latest[0], latest[3]))
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise


def issue(verifier_db, custodian_db, receipt_raw, *, ttl_seconds=300, now=None):
    if (type(ttl_seconds) is not int
            or not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS):
        raise ValueError('invalid challenge lifetime')
    latest = _latest_with_receipt(custodian_db, receipt_raw)
    timestamp = _now(now)
    with closing(_connect(verifier_db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            seq = _ready(con, latest)
            nonce = secrets.token_hex(16)
            con.execute(
                'INSERT INTO challenges(nonce, issued_at, expires_at)'
                ' VALUES(?,?,?)', (nonce, timestamp, timestamp + ttl_seconds))
            digest = _checkpoint_digest(con)
            con.execute(
                'UPDATE receipt_gate SET pending_sequence=?,'
                ' pending_checkpoint_sha256=? WHERE slot=1',
                (seq + 1, digest))
            con.commit()
            return nonce
        except Exception:
            con.rollback()
            raise


def accept(verifier_db, custodian_db, receipt_raw, exe, temporal_raw,
           binding_raw, before_raw, after_raw, provenance_raw,
           before_receipt_raw, after_receipt_raw, *, now=None):
    # The complete stage-243 provenance/temporal/stream gate always runs.
    prior = audit_provenance(
        exe, temporal_raw, binding_raw, before_raw, after_raw,
        provenance_raw, before_receipt_raw, after_receipt_raw)
    if not prior['all_supplied_provenance_claims_consistent']:
        return False
    nonce = _json_object(provenance_raw, MAX_PROVENANCE_BYTES)['session_nonce']
    timestamp = _now(now)
    before_hash, after_hash = _sha(before_raw), _sha(after_raw)
    if before_hash == after_hash:
        raise ValueError('identical capture stream digests')
    latest = _latest_with_receipt(custodian_db, receipt_raw)
    with closing(_connect(verifier_db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            seq = _ready(con, latest)
            item = con.execute(
                'SELECT issued_at,expires_at,consumed FROM challenges'
                ' WHERE nonce=?', (nonce,)).fetchone()
            if (item is None or item[2] or timestamp < item[0]
                    or timestamp >= item[1]):
                con.rollback()
                return False
            con.execute(
                'INSERT INTO accepted(nonce,provenance_sha256,accepted_at)'
                ' VALUES(?,?,?)', (nonce, _sha(provenance_raw), timestamp))
            con.execute('INSERT INTO accepted_streams VALUES(?,?)', (before_hash, nonce))
            con.execute('INSERT INTO accepted_streams VALUES(?,?)', (after_hash, nonce))
            n = con.execute('UPDATE challenges SET consumed=1'
                            ' WHERE nonce=? AND consumed=0', (nonce,)).rowcount
            if n != 1:
                con.rollback()
                return False
            digest = _checkpoint_digest(con)
            con.execute(
                'UPDATE receipt_gate SET pending_sequence=?,'
                ' pending_checkpoint_sha256=? WHERE slot=1', (seq + 1, digest))
            con.commit()
            return True
        except sqlite3.IntegrityError:
            con.rollback()
            return False
        except Exception:
            con.rollback()
            raise


def acknowledge(verifier_db, custodian_db, receipt_raw):
    """Consume pending marker only after matching committed custodian receipt."""
    latest = _latest_with_receipt(custodian_db, receipt_raw)
    with closing(_connect(verifier_db)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            seq, receipt_hash, pending_seq, pending_digest = _guard(con)
            if pending_seq is None:
                if (seq == latest[0] and receipt_hash == latest[3]
                        and _checkpoint_digest(con) == latest[1]):
                    con.commit()
                    return False  # Safe idempotent acknowledgment
                raise AnchorConflict('custodian moved without pending verifier handoff')
            if (pending_seq != latest[0]
                    or receipt_hash != latest[2]
                    or pending_digest != latest[1]
                    or _checkpoint_digest(con) != latest[1]):
                raise AnchorConflict('custodian receipt does not anchor pending commit')
            con.execute(
                'UPDATE receipt_gate SET ack_sequence=?,ack_receipt_sha256=?,'
                'pending_sequence=NULL,pending_checkpoint_sha256=NULL WHERE slot=1',
                (latest[0], latest[3]))
            con.commit()
            return True
        except Exception:
            con.rollback()
            raise


def _report(*, bootstrapped=False, issued=False, accepted=False,
            acknowledged=False, already_acknowledged=False, blocked=False):
    return {
        'schema': REPORT_SCHEMA,
        'bootstrap_committed': bool(bootstrapped),
        'challenge_issued_with_pending_anchor': bool(issued),
        'capture_accepted_with_pending_anchor': bool(accepted),
        'custodian_acknowledgment_recorded': bool(acknowledged),
        'recovered_existing_acknowledgment': bool(already_acknowledged),
        'further_admission_blocked': bool(blocked),
        'independent_custodian_identity_authenticated': False,
        'cross_database_atomic_commit_guaranteed': False,
        'legacy_commands_protected_by_this_gate': False,
        'external_rollback_prevention_guaranteed': False,
        'original_ps1_execution_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_nonces_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('bootstrap', 'issue', 'accept', 'ack'):
        p = sub.add_parser(mode)
        p.add_argument('verifier_database', type=Path)
        p.add_argument('custodian_database', type=Path)
        p.add_argument('private_latest_receipt', type=Path)
        if mode == 'issue':
            p.add_argument('--ttl-seconds', type=int, default=300)
        if mode == 'accept':
            for name in ('disc', 'inventory', 'temporal_claim', 'binding_manifest',
                         'before_stream', 'after_stream', 'provenance',
                         'before_receipt', 'after_receipt'):
                p.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt_raw = _read_limited(_private_regular_file(args.private_latest_receipt),
                                    MAX_RECEIPT_BYTES)
        if args.mode == 'bootstrap':
            bootstrap(args.verifier_database, args.custodian_database, receipt_raw)
            report, status = _report(bootstrapped=True), 0
        elif args.mode == 'issue':
            nonce = issue(args.verifier_database, args.custodian_database, receipt_raw,
                          ttl_seconds=args.ttl_seconds)
            # Only the issuer emits the new nonce for a PRIVATE collector handoff.
            print(json.dumps({
                'schema': ISSUE_SCHEMA, 'session_nonce': nonce,
                'pending_custodian_acknowledgment': True,
                'independent_custodian_identity_authenticated': False,
            }, sort_keys=True))
            return 0
        elif args.mode == 'ack':
            changed = acknowledge(args.verifier_database, args.custodian_database,
                                  receipt_raw)
            report, status = _report(
                acknowledged=changed, already_acknowledged=not changed), 0
        else:
            entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
            matches = [row for row in entries if type(row) is dict
                       and row.get('path') == '/EXE/WILDARMS.EXE;1'
                       and not row.get('directory', False)]
            if len(matches) != 1:
                raise ValueError('missing original EXE inventory entry')
            raw = (read_raw_iso_entry(args.disc, matches[0]),
                   _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
                   _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
                   _read_limited(args.before_stream, MAX_STREAM_BYTES),
                   _read_limited(args.after_stream, MAX_STREAM_BYTES),
                   _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
                   _read_limited(args.before_receipt, MAX_COLLECTOR_RECEIPT_BYTES),
                   _read_limited(args.after_receipt, MAX_COLLECTOR_RECEIPT_BYTES))
            accepted = accept(args.verifier_database, args.custodian_database,
                              receipt_raw, *raw)
            report, status = _report(accepted=accepted), 0 if accepted else 1
    except (PendingHandoff, AnchorConflict):
        report, status = _report(blocked=True), 1
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, sqlite3.Error):
        report, status = {
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_nonces_or_values_emitted': False,
        }, 2
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
