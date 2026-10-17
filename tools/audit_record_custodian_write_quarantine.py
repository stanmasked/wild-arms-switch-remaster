"""Durable, non-expiring custody WRITE quarantine (stage-263B research).

Install an exact-request quarantine in the same custody SQLite writer
transaction used to verify the negative outcome. Integrated custody writers
check the quarantine under their own BEGIN IMMEDIATE before every mutation.
No removal, expiration or witness-fence retirement API is provided.

IMPORTANT: a signed supervisor stop *claim* cannot prove OS quiescence.
Older executables, direct SQL access and independent services can bypass
this Python-only gate; not sufficient for administrative fence release.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_anchor_handoff import _canonical, GENESIS
    from .audit_record_capture_stream_binding import _digest, _read_limited, _sha
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_recovery_witness import _witness_rows
    from .audit_record_witness_fence import _fence_row, _owner
    from .audit_record_witness_fence_reconciliation import (
        _audit, _original, _request_digest, MAX_ORIGINAL_REQUEST,
    )
    from .audit_record_witness_fence_quiescence import (
        _verified_stop, _negative_state, MAX_STOP, PreflightConflict,
    )
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_anchor_handoff import _canonical, GENESIS
    from audit_record_capture_stream_binding import _digest, _read_limited, _sha
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_recovery_witness import _witness_rows
    from audit_record_witness_fence import _fence_row, _owner
    from audit_record_witness_fence_reconciliation import (
        _audit, _original, _request_digest, MAX_ORIGINAL_REQUEST,
    )
    from audit_record_witness_fence_quiescence import (
        _verified_stop, _negative_state, MAX_STOP, PreflightConflict,
    )

SCHEMA = 'wild-arms-ps1-custodian-write-quarantine-v1'
EVENT_DOMAIN = b'wild-arms-ps1-custodian-write-quarantine-v1\x00'
REPORT_SCHEMA = 'wild-arms-ps1-custodian-write-quarantine-report-v1'
# A second, transactionally committed SQLite header marker. This detects an
# accidentally dropped quarantine table or erased header marker, NOT a
# privileged rewrite of both artifacts or a restored older database.
QUARANTINE_USER_VERSION = 0x5741524D  # "WARM", within signed int32.
COLUMNS = {
    'slot', 'schema', 'custody_request_sha256', 'fence_owner_sha256',
    'signed_stop_sha256', 'negative_classification',
    'witness_count', 'witness_chain_sha256', 'quarantine_event_sha256',
}


class QuarantineConflict(ValueError):
    """All custody writes must refuse a sealed writer quarantine."""


def _quarantine_row(con):
    version = con.execute('PRAGMA user_version').fetchone()[0]
    if type(version) is not int or version not in (0, QUARANTINE_USER_VERSION):
        raise QuarantineConflict('unexpected custody database version marker')
    table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='custodian_writer_quarantine'").fetchone()
    if table is None:
        if version == QUARANTINE_USER_VERSION:
            raise QuarantineConflict('quarantine table missing but header remains sealed')
        return None
    if version != QUARANTINE_USER_VERSION:
        raise QuarantineConflict('quarantine table present without sealed header')
    cols = {r[1] for r in con.execute(
        'PRAGMA table_info("custodian_writer_quarantine")')}
    if cols != COLUMNS:
        raise QuarantineConflict('invalid custodian quarantine table schema')
    rows = con.execute(
        'SELECT slot,schema,custody_request_sha256,fence_owner_sha256,'
        'signed_stop_sha256,negative_classification,witness_count,'
        'witness_chain_sha256,quarantine_event_sha256'
        ' FROM custodian_writer_quarantine').fetchall()
    if len(rows) != 1:
        raise QuarantineConflict('missing or multiple custodian quarantine records')
    row = rows[0]
    if (row[0] != 1 or row[1] != SCHEMA
            or row[5] not in (
                'reservation-not-observed-in-snapshot',
                'checkpoint-not-committed-in-snapshot')
            or type(row[6]) is not int or row[6] < 0):
        raise QuarantineConflict('invalid custodian quarantine record')
    for field in (row[2], row[3], row[4], row[7], row[8]):
        _digest(field)
    event = dict(zip((
        'slot', 'schema', 'custody_request_sha256', 'fence_owner_sha256',
        'signed_stop_sha256', 'negative_classification', 'witness_count',
        'witness_chain_sha256'), row[:-1]))
    expected = hashlib.sha256(EVENT_DOMAIN + _canonical(event)).hexdigest()
    if expected != row[-1]:
        raise QuarantineConflict('corrupt custody write quarantine')
    return row


def require_unquarantined(con):
    """Call while holding BEGIN IMMEDIATE on custody DB, before mutation."""
    if _quarantine_row(con) is not None:
        raise QuarantineConflict('custodian is durably write-quarantined')


def install(custodian_db, witness_db, original_raw, signed_stop_raw,
            supervisor_public, supervisor_pin, *, supervisor_tag):
    """Install fail-closed gate only after exact negative snapshot and witness check."""
    req, _ = _original(original_raw)
    _verified_stop(original_raw, signed_stop_raw, supervisor_public,
                   supervisor_pin, supervisor_tag)
    with closing(_connect(custodian_db)) as custody:
        custody.execute('BEGIN IMMEDIATE')
        try:
            require_unquarantined(custody)
            classification = _negative_state(custody, original_raw)
            with closing(_connect(witness_db)) as witness:
                witness.execute('BEGIN IMMEDIATE')
                try:
                    rows = _witness_rows(witness)
                    _audit(witness)
                    fence = _fence_row(witness)
                    head = (len(rows), rows[-1][4] if rows else GENESIS)
                    if (fence is None or
                            (fence[1], fence[2], fence[3], fence[4]) != (
                                _owner(req['request_id']),
                                _request_digest(original_raw), *head)):
                        raise PreflightConflict('original witness fence not present')
                finally:
                    witness.rollback()
            event = {
                'slot': 1, 'schema': SCHEMA,
                'custody_request_sha256': _request_digest(original_raw),
                'fence_owner_sha256': _owner(req['request_id']),
                'signed_stop_sha256': _sha(signed_stop_raw),
                'negative_classification': classification,
                'witness_count': head[0],
                'witness_chain_sha256': head[1],
            }
            event_sha = hashlib.sha256(
                EVENT_DOMAIN + _canonical(event)).hexdigest()
            custody.execute("""CREATE TABLE custodian_writer_quarantine (
                slot INTEGER PRIMARY KEY CHECK(slot=1),
                schema TEXT NOT NULL,
                custody_request_sha256 TEXT NOT NULL,
                fence_owner_sha256 TEXT NOT NULL,
                signed_stop_sha256 TEXT NOT NULL,
                negative_classification TEXT NOT NULL,
                witness_count INTEGER NOT NULL CHECK(witness_count>=0),
                witness_chain_sha256 TEXT NOT NULL,
                quarantine_event_sha256 TEXT NOT NULL
            )""")
            custody.execute(
                'INSERT INTO custodian_writer_quarantine VALUES (?,?,?,?,?,?,?,?,?)',
                (*event.values(), event_sha))
            # SQLite header metadata is transactional: rollback restores both
            # header and table if installation fails before commit.
            custody.execute(f'PRAGMA user_version={QUARANTINE_USER_VERSION}')
            if _quarantine_row(custody) is None:
                raise QuarantineConflict('write gate install not persisted')
            custody.commit()
        except Exception:
            custody.rollback()
            raise
    return {
        'schema': REPORT_SCHEMA,
        'custody_writer_quarantine_installed': True,
        'negative_snapshot_classification': classification,
        'instrumented_writers_blocked': True,
        'external_process_quiescence_independently_proved': False,
        'all_entrypoints_durably_disabled': False,
        'witness_fence_retired': False,
        'safe_to_reconcile_negative_outcome': False,
        'native_switch_game_build_verified': False,
        'private_credentials_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('custodian_database', type=Path)
    parser.add_argument('witness_database', type=Path)
    parser.add_argument('original_private_request', type=Path)
    parser.add_argument('signed_supervisor_stop_claim', type=Path)
    parser.add_argument('pinned_supervisor_public_pem', type=Path)
    parser.add_argument('trusted_supervisor_pem_sha256')
    parser.add_argument('--supervisor-tag', required=True)
    args = parser.parse_args(argv)
    try:
        report = install(
            args.custodian_database, args.witness_database,
            _read_limited(_private_regular_file(args.original_private_request),
                          MAX_ORIGINAL_REQUEST),
            _read_limited(_private_regular_file(args.signed_supervisor_stop_claim),
                          MAX_STOP),
            args.pinned_supervisor_public_pem,
            args.trusted_supervisor_pem_sha256,
            supervisor_tag=args.supervisor_tag)
        code = 0
    except (QuarantineConflict, PreflightConflict):
        report, code = {'schema': REPORT_SCHEMA, 'write_quarantine_blocked': True,
                        'witness_fence_retired': False}, 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            IndexError, sqlite3.Error, OverflowError):
        report, code = {'schema': REPORT_SCHEMA, 'valid_input': False,
                        'witness_fence_retired': False}, 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
