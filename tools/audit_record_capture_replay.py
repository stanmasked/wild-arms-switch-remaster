"""Conservative, read-only replay collision audit for private PS1 captures.

The challenge and history MUST be sourced from a verifier-controlled
channel/store to give meaningful freshness protection. This tool cannot
authenticate their issuance, freshness, completeness, or trustworthiness.
Stage 243 is always rerun. No raw private values are emitted or written.
"""
import argparse
import json
from pathlib import Path

try:
    from .audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, _nonce, _tag,
        MAX_PROVENANCE_BYTES, MAX_RECEIPT_BYTES,
    )
    from .audit_record_capture_stream_binding import (
        _read_limited, _sha, _digest, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
except ImportError:
    from audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, _nonce, _tag,
        MAX_PROVENANCE_BYTES, MAX_RECEIPT_BYTES,
    )
    from audit_record_capture_stream_binding import (
        _read_limited, _sha, _digest, MAX_STREAM_BYTES, MAX_MANIFEST_BYTES,
    )
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES

CHALLENGE_SCHEMA = 'wild-arms-ps1-verifier-challenge-v1'
LEDGER_SCHEMA = 'wild-arms-ps1-accepted-capture-ledger-v1'
REPORT_SCHEMA = 'wild-arms-ps1-capture-replay-audit-v1'
MAX_CHALLENGE_BYTES = 4096
MAX_LEDGER_BYTES = 256 * 1024
MAX_LEDGER_ENTRIES = 512
LEDGER_FIELDS = frozenset({
    'session_nonce', 'provenance_sha256',
    'before_stream_sha256', 'after_stream_sha256',
})


def _check_challenge(raw):
    challenge = _json_object(raw, MAX_CHALLENGE_BYTES)
    if (set(challenge) != {
            'schema', 'session_nonce', 'verifier_tag', 'capture_kind'}
            or challenge['schema'] != CHALLENGE_SCHEMA
            or challenge['capture_kind'] != 'record-slot-samples'):
        raise ValueError('invalid verifier challenge schema')
    _nonce(challenge['session_nonce'])
    _tag(challenge['verifier_tag'])
    return challenge


def _check_ledger(raw):
    ledger = _json_object(raw, MAX_LEDGER_BYTES)
    if set(ledger) != {'schema', 'accepted_sessions'} or ledger['schema'] != LEDGER_SCHEMA:
        raise ValueError('invalid accepted session ledger schema')
    rows = ledger['accepted_sessions']
    if type(rows) is not list or len(rows) > MAX_LEDGER_ENTRIES:
        raise ValueError('invalid bounded accepted session ledger')
    seen_nonces, seen_provenance, seen_before, seen_after = (
        set(), set(), set(), set())
    validated = []
    for row in rows:
        if type(row) is not dict or set(row) != LEDGER_FIELDS:
            raise ValueError('invalid accepted session ledger entry')
        nonce = _nonce(row['session_nonce'])
        provenance = _digest(row['provenance_sha256'])
        before = _digest(row['before_stream_sha256'])
        after = _digest(row['after_stream_sha256'])
        if (nonce in seen_nonces or provenance in seen_provenance
                or before in seen_before or after in seen_after
                or before == after):
            raise ValueError('reused or inconsistent accepted session entry')
        seen_nonces.add(nonce)
        seen_provenance.add(provenance)
        seen_before.add(before)
        seen_after.add(after)
        validated.append(row)
    return validated


def analyze(exe, temporal_raw, binding_raw, before_raw, after_raw,
            provenance_raw, before_receipt_raw, after_receipt_raw,
            challenge_raw, ledger_raw):
    """Compare stage-243 capture to a *provided* verifier challenge and ledger.

    Pure audit, without registering a run or consuming a challenge.
    The verifier must maintain an independently protected, atomic history
    and its own one-use challenge inventory for any real anti-replay guarantee.
    """
    prior = audit_provenance(
        exe, temporal_raw, binding_raw, before_raw, after_raw,
        provenance_raw, before_receipt_raw, after_receipt_raw)
    provenance = _json_object(provenance_raw, MAX_PROVENANCE_BYTES)
    challenge = _check_challenge(challenge_raw)
    previous = _check_ledger(ledger_raw)

    nonce = provenance['session_nonce']
    challenge_matches = challenge['session_nonce'] == nonce
    old_nonces = {r['session_nonce'] for r in previous}
    old_provenances = {r['provenance_sha256'] for r in previous}
    old_before = {r['before_stream_sha256'] for r in previous}
    old_after = {r['after_stream_sha256'] for r in previous}
    replay_found = (
        nonce in old_nonces or _sha(provenance_raw) in old_provenances
        or _sha(before_raw) in old_before or _sha(after_raw) in old_after
    )
    accepted = bool(prior['all_supplied_provenance_claims_consistent']
                    and challenge_matches and not replay_found)
    return {
        'schema': REPORT_SCHEMA,
        'stage_243_provenance_claims_consistent':
            prior['all_supplied_provenance_claims_consistent'],
        'verifier_challenge_matches_claimed_session': challenge_matches,
        'accepted_session_ledger_entries_checked': len(previous),
        'reused_session_or_stream_detected_in_supplied_ledger': bool(replay_found),
        'eligible_against_supplied_replay_inputs': accepted,
        'challenge_issuance_independently_authenticated': False,
        'ledger_integrity_independently_authenticated': False,
        'durable_one_time_acceptance_recorded': False,
        'replay_prevention_guaranteed': False,
        'collector_receipts_cryptographically_authenticated': False,
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
    parser.add_argument('verifier_challenge', type=Path)
    parser.add_argument('accepted_session_ledger', type=Path)
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
            _read_limited(args.after_receipt, MAX_RECEIPT_BYTES),
            _read_limited(args.verifier_challenge, MAX_CHALLENGE_BYTES),
            _read_limited(args.accepted_session_ledger, MAX_LEDGER_BYTES))
    except (OSError, ValueError, UnicodeError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_addresses_or_values_emitted': False},
            sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['eligible_against_supplied_replay_inputs'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
