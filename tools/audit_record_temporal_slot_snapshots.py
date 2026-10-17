"""Conservative chronology check for *claimed* PS1 global-slot RAM snapshots.

Separate collection labels and chronological counters are still user
assertions, not authenticated or independent PlayStation observations.
Only aggregate, non-sensitive results leave this tool.
"""
import argparse
import json
import re
from pathlib import Path

try:
    from .audit_record_global_slot_witness import (
        analyze as audit_slot, _global_slot_opcode_address, read_raw_iso_entry,
        MAX_REFERENCE_BYTES, MAX_CLAIMS,
    )
    from .audit_record_executed_access_claims import _read_site_words, _SITES
    from .audit_record_address_deltas import _address
except ImportError:
    from audit_record_global_slot_witness import (
        analyze as audit_slot, _global_slot_opcode_address, read_raw_iso_entry,
        MAX_REFERENCE_BYTES, MAX_CLAIMS,
    )
    from audit_record_executed_access_claims import _read_site_words, _SITES
    from audit_record_address_deltas import _address

SCHEMA = 'wild-arms-ps1-temporal-slot-snapshot-claims-v1'
REPORT_SCHEMA = 'wild-arms-ps1-temporal-slot-snapshot-audit-v1'
_TAG = re.compile(r'[A-Za-z0-9_-]{1,32}\Z')
_MAX_SEQUENCE = 0xffffffff
_READ_FIELDS = frozenset({
    'at_pc_u32', 'slot_address_u32', 'slot_word_u32',
    'event_sequence', 'collector_tag',
})
_WINDOW_FIELDS = frozenset({
    'site', 'record_index', 'execution_tag',
    'lw_event_sequence', 'before', 'after',
})


def _event_number(value):
    if type(value) is not int or not 0 <= value <= _MAX_SEQUENCE:
        raise ValueError('invalid private event sequence')
    return value


def _tag(value):
    if type(value) is not str or not _TAG.fullmatch(value):
        raise ValueError('invalid private collector/trace tag')
    return value


def _read_snapshot(snapshot):
    if type(snapshot) is not dict or set(snapshot) != _READ_FIELDS:
        raise ValueError('invalid bounded private snapshot fields')
    return {
        'pc': _address(snapshot['at_pc_u32']),
        'slot': _address(snapshot['slot_address_u32']),
        'word': _address(snapshot['slot_word_u32']),
        'seq': _event_number(snapshot['event_sequence']),
        'collector': _tag(snapshot['collector_tag']),
    }


def analyze(exe, reference):
    """Check claimed before/LW/after ordering and stable RAM-slot words.

    Every (site,index) has exactly one before/after pair. A snapshot
    marked "before" must be at the global LW PC; "after" must be at
    PC+8, *after* the independent SLL gap. Both claimed reads must
    target the precise EXE-derived virtual slot and agree with the
    previously claimed loaded value. No overlapping event windows.
    """
    if (type(reference) is not dict or set(reference) != {
            'schema', 'slot_claim', 'read_windows'}
            or reference.get('schema') != SCHEMA):
        raise ValueError('invalid temporal snapshot claim schema')
    windows = reference['read_windows']
    if type(windows) is not list or not 6 <= len(windows) <= MAX_CLAIMS:
        raise ValueError('invalid bounded snapshot window count')

    prior = audit_slot(exe, reference['slot_claim'])
    slots = reference['slot_claim']['slot_witnesses']
    known = {(r['site'], r['record_index']): r for r in slots}
    if len(known) != len(windows) or len(known) != len(slots):
        raise ValueError('missing or repeated source slot samples')

    sequence_windows = []
    all_trace_tags = set()
    mapped = {}
    for window in windows:
        if (type(window) is not dict or set(window) != _WINDOW_FIELDS
                or type(window['site']) is not str
                or type(window['record_index']) is not int):
            raise ValueError('invalid temporal window fields')
        key = (window['site'], window['record_index'])
        if key not in known or key in mapped:
            raise ValueError('duplicate or foreign temporal window')
        tag = _tag(window['execution_tag'])
        if tag in all_trace_tags:
            raise ValueError('reused private execution tag')
        all_trace_tags.add(tag)
        before = _read_snapshot(window['before'])
        after = _read_snapshot(window['after'])
        lw_seq = _event_number(window['lw_event_sequence'])
        if not before['seq'] < lw_seq < after['seq']:
            raise ValueError('invalid private memory read ordering')
        sequence_windows.append((before['seq'], lw_seq, after['seq']))
        mapped[key] = (before, after)

    # This does not authenticate the claimed event clock; it merely
    # prohibits impossible overlapping sample windows in that clock.
    timeline = sorted(sequence_windows)
    for earlier, later in zip(timeline, timeline[1:]):
        if earlier[-1] >= later[0]:
            raise ValueError('interleaved or reused capture event sequence')

    base = int.from_bytes(exe[0x18:0x1c], 'little')
    size = int.from_bytes(exe[0x1c:0x20], 'little')
    slot_by_site = {}
    for site, _ in mapped:
        if site not in slot_by_site:
            words = _read_site_words(exe, base, size, _SITES[site])
            slot_by_site[site] = _global_slot_opcode_address(words)[1]

    matching = distinct_collector_pairs = 0
    for (site, index), (before, after) in mapped.items():
        witness = known[(site, index)]
        expected_pc = _SITES[site] + 36
        expected_after_pc = expected_pc + 8
        derived_slot = slot_by_site[site]
        expected_value = _address(witness['slot_memory_word_u32'])
        collector_distinct = before['collector'] != after['collector']
        distinct_collector_pairs += bool(collector_distinct)
        if (before['pc'] == expected_pc
                and after['pc'] == expected_after_pc
                and before['slot'] == derived_slot
                and after['slot'] == derived_slot
                and before['word'] == expected_value
                and after['word'] == expected_value
                and collector_distinct):
            matching += 1

    return {
        'schema': REPORT_SCHEMA,
        'code_sites_with_exe_derived_slots': len(slot_by_site),
        'claimed_snapshot_windows_checked': len(mapped),
        'claimed_distinct_collector_pairs': distinct_collector_pairs,
        'temporal_slot_snapshot_pairs_matching': matching,
        'claimed_event_sequences_nonoverlapping': True,
        'prior_global_slot_claims_consistent':
            prior['all_private_global_slot_claims_consistent'],
        'all_claimed_temporal_snapshots_consistent': bool(
            prior['all_private_global_slot_claims_consistent']
            and matching == len(mapped)),
        'independent_collection_provenance_authenticated': False,
        'memory_contents_independently_observed': False,
        'original_ps1_execution_verified': False,
        'original_game_record_size_verified': False,
        'native_nintendo_switch_build_verified': False,
        'private_addresses_or_values_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('private_snapshot_claims', type=Path)
    args = parser.parse_args(argv)
    try:
        inventory = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        found = [row for row in inventory if type(row) is dict
                 and row.get('path') == '/EXE/WILDARMS.EXE;1'
                 and not row.get('directory', False)]
        if len(found) != 1:
            raise ValueError('missing private game executable')
        with args.private_snapshot_claims.open('rb') as f:
            data = f.read(MAX_REFERENCE_BYTES + 1)
        if len(data) > MAX_REFERENCE_BYTES:
            raise ValueError('oversized private snapshot claim')
        result = analyze(read_raw_iso_entry(args.disc, found[0]),
                         json.loads(data.decode('utf-8')))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_addresses_or_values_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['all_claimed_temporal_snapshots_consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
