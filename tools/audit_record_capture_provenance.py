"""Bind *claimed* debugger-session provenance to stage-242 raw capture streams.

All metadata and collector receipts are supplied by the caller. This checks
self-consistency, NOT debugger authenticity, independent collection, or real
PlayStation execution. Never print private identifiers or file contents.
"""
import argparse
import json
import re
from pathlib import Path

try:
    from .audit_record_capture_stream_binding import (
        analyze as audit_streams, _parse, _sha, _digest, _tag, _rows,
        _read_limited, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
except ImportError:
    from audit_record_capture_stream_binding import (
        analyze as audit_streams, _parse, _sha, _digest, _tag, _rows,
        _read_limited, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES

SCHEMA = 'wild-arms-ps1-session-provenance-v1'
RECEIPT_SCHEMA = 'wild-arms-ps1-collector-receipt-v1'
REPORT_SCHEMA = 'wild-arms-ps1-session-provenance-audit-v1'
MAX_PROVENANCE_BYTES = 8192
MAX_RECEIPT_BYTES = 4096
_NONCE = re.compile(r'[0-9a-f]{32}\Z')
_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+\-]{0,39}\Z')
_CONDITIONS = {
    'target_kind': {'emulator', 'hardware', 'unknown'},
    'cpu_backend': {'interpreter', 'dynarec', 'unknown'},
    'event_clock': {'instruction-order', 'debugger-counter', 'unknown'},
    'sample_mode': {'halted-breakpoint', 'step-then-sample', 'unknown'},
}
_RECEIPT_FIELDS = {
    'schema', 'role', 'session_nonce', 'collector_tag',
    'provenance_sha256', 'stream_sha256', 'observed_rows',
    'first_event_sequence', 'last_event_sequence',
}


def _json_object(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ValueError('invalid bounded private provenance input')
    value = _parse(raw)
    if type(value) is not dict:
        raise ValueError('invalid private provenance object')
    return value


def _nonce(value):
    if type(value) is not str or not _NONCE.fullmatch(value) or value == '0' * 32:
        raise ValueError('invalid private session nonce')
    return value


def _version(value):
    if type(value) is not str or not _VERSION.fullmatch(value):
        raise ValueError('invalid private debugger identity field')
    return value


def analyze(exe, temporal_raw, binding_raw, before_raw, after_raw,
            provenance_raw, before_receipt_raw, after_receipt_raw):
    """Audit exact bytes and *asserted* provenance, never authenticate source."""
    # Run the whole old gate unmodified, including EXE/temporal comparison.
    prior = audit_streams(exe, temporal_raw, binding_raw, before_raw, after_raw)
    binding = _json_object(binding_raw, MAX_MANIFEST_BYTES)
    provenance = _json_object(provenance_raw, MAX_PROVENANCE_BYTES)
    if (set(provenance) != {
            'schema', 'session_nonce', 'stream_binding_manifest_sha256',
            'debugger', 'capture_conditions'} or provenance['schema'] != SCHEMA):
        raise ValueError('invalid private session provenance schema')
    nonce = _nonce(provenance['session_nonce'])
    if _digest(provenance['stream_binding_manifest_sha256']) != _sha(binding_raw):
        raise ValueError('private provenance binding digest mismatch')
    debugger = provenance['debugger']
    if (type(debugger) is not dict
            or set(debugger) != {'name', 'version', 'binary_sha256', 'platform'}):
        raise ValueError('invalid private debugger declaration')
    _tag(debugger['name'])
    _version(debugger['version'])
    _digest(debugger['binary_sha256'])
    _version(debugger['platform'])
    conditions = provenance['capture_conditions']
    if (type(conditions) is not dict
            or set(conditions) != set(_CONDITIONS)):
        raise ValueError('invalid private capture conditions')
    for key, choices in _CONDITIONS.items():
        if type(conditions[key]) is not str or conditions[key] not in choices:
            raise ValueError('invalid private capture condition')

    stream_meta = {entry['role']: entry for entry in binding['streams']}
    for role, stream, receipt_raw in (
            ('before', before_raw, before_receipt_raw),
            ('after', after_raw, after_receipt_raw)):
        receipt = _json_object(receipt_raw, MAX_RECEIPT_BYTES)
        if set(receipt) != _RECEIPT_FIELDS or receipt['schema'] != RECEIPT_SCHEMA:
            raise ValueError('invalid private collector receipt schema')
        if (receipt['role'] != role
                or receipt['session_nonce'] != nonce
                or receipt['collector_tag'] != stream_meta[role]['collector_tag']
                or _digest(receipt['provenance_sha256']) != _sha(provenance_raw)
                or _digest(receipt['stream_sha256']) != _sha(stream)):
            raise ValueError('private collector receipt mismatch')
        # Stage 242 validates session labels, ordered counters, and full
        # coverage before the receipts are checked; still recount here.
        rows = list(_rows(
            stream, session=binding['session_tag'],
            collector=stream_meta[role]['collector_tag'],
            expected_count=prior['claimed_window_pairs_checked']).values())
        if (type(receipt['observed_rows']) is not int
                or receipt['observed_rows'] != len(rows)
                or type(receipt['first_event_sequence']) is not int
                or receipt['first_event_sequence'] != rows[0]['event_sequence']
                or type(receipt['last_event_sequence']) is not int
                or receipt['last_event_sequence'] != rows[-1]['event_sequence']):
            raise ValueError('private collector receipt counters mismatch')

    # All claims in these files can be rewritten by whoever controls them.
    # Never report the debugger, binary hash, session nonce or conditions.
    return {
        'schema': REPORT_SCHEMA,
        'stage_242_stream_claims_consistent':
            prior['all_supplied_stream_claims_consistent'],
        'exact_stream_binding_manifest_checked': True,
        'claimed_debugger_identity_fields_checked': True,
        'claimed_capture_conditions_checked': True,
        'session_nonce_matches_both_receipts': True,
        'collector_receipts_bound_to_raw_streams': 2,
        'claimed_capture_rows_checked': prior['claimed_stream_rows_checked'],
        'all_supplied_provenance_claims_consistent':
            prior['all_supplied_stream_claims_consistent'],
        'debugger_binary_independently_verified': False,
        'capture_conditions_independently_observed': False,
        'collector_receipts_cryptographically_authenticated': False,
        'session_origin_independently_authenticated': False,
        'original_ps1_execution_verified': False,
        'original_game_record_size_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_addresses_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('temporal_claim', type=Path)
    parser.add_argument('binding_manifest', type=Path)
    parser.add_argument('before_stream', type=Path)
    parser.add_argument('after_stream', type=Path)
    parser.add_argument('provenance', type=Path)
    parser.add_argument('before_receipt', type=Path)
    parser.add_argument('after_receipt', type=Path)
    args = parser.parse_args(argv)
    try:
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        found = [row for row in entries if type(row) is dict
                 and row.get('path') == '/EXE/WILDARMS.EXE;1'
                 and not row.get('directory', False)]
        if len(found) != 1:
            raise ValueError('expected exactly one original EXE entry')
        exe = read_raw_iso_entry(args.disc, found[0])
        result = analyze(
            exe, _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
            _read_limited(args.binding_manifest, MAX_MANIFEST_BYTES),
            _read_limited(args.before_stream, MAX_STREAM_BYTES),
            _read_limited(args.after_stream, MAX_STREAM_BYTES),
            _read_limited(args.provenance, MAX_PROVENANCE_BYTES),
            _read_limited(args.before_receipt, MAX_RECEIPT_BYTES),
            _read_limited(args.after_receipt, MAX_RECEIPT_BYTES))
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_addresses_or_values_emitted': False},
            sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['all_supplied_provenance_claims_consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
