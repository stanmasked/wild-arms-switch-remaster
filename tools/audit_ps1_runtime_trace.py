#!/usr/bin/env python3
"""Validate a private PS1 debugger event log against a real RAM snapshot.

The trace is user-supplied and not cryptographically attested. This validator
can correlate recorded events and bytes; it cannot prove their origin or game
execution on its own. It never exports original payload bytes.
"""
import argparse
import json
from pathlib import Path

from verify_ps1_ram_container_snapshot import compare_private_ram

SLOT = 0x800D2EA0
TRANSFER_TARGET = 0x8002356C
BUFFER = 0x80183000
BUFFER_BYTES = 0x3A000
CDFLR_LBA = 38503
CDFLR_SECTORS = 7772
MAX_EVENTS = 100000
ALLOWED = frozenset(('watchpoint_write', 'transfer_call', 'disc_read', 'ram_snapshot'))


def _uint(value, field):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and value.startswith(('0x', '0X')):
        try:
            number = int(value, 16)
        except ValueError as exc:
            raise ValueError(f'{field}: invalid hexadecimal integer') from exc
    else:
        raise ValueError(f'{field}: expected integer or 0x hexadecimal string')
    if not 0 <= number <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f'{field}: number outside unsigned 64-bit range')
    return number


def _ps1_ram_pointer(address):
    return ((0x80000000 <= address < 0x80200000) or
            (0xA0000000 <= address < 0xA0200000))


def audit_capture(trace_file, container, raw_ram, *, buffer=BUFFER,
                  count=BUFFER_BYTES, cdflr_lba=CDFLR_LBA,
                  cdflr_sectors=CDFLR_SECTORS):
    trace_file = Path(trace_file)
    if trace_file.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('trace JSON exceeds 8MiB safety limit')
    trace = json.loads(trace_file.read_text(encoding='utf-8'))
    if not isinstance(trace, dict) or trace.get('schema') != 1 or trace.get('kind') != 'PRIVATE_PS1_RUNTIME_EVENTS':
        raise ValueError('expected PRIVATE_PS1_RUNTIME_EVENTS schema 1')
    events = trace.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError('trace events must be a bounded nonempty array')
    if type(count) is not int or not 1 <= count <= 0x3A000:
        raise ValueError('count must be a bounded positive byte count')
    if not _ps1_ram_pointer(buffer) or (buffer & 3):
        raise ValueError('buffer must be four-byte-aligned KSEG0/KSEG1 PS1 RAM')
    if (type(cdflr_lba) is not int or type(cdflr_sectors) is not int or
            cdflr_lba < 0 or cdflr_sectors <= 0):
        raise ValueError('invalid catalogued CDFLR sector range')

    normalized = []
    prev_tick = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get('kind') not in ALLOWED:
            raise ValueError(f'event {index}: unexpected kind')
        tick = _uint(event.get('tick'), f'event {index}.tick')
        if tick <= prev_tick:
            raise ValueError('event ticks must be strictly increasing')
        prev_tick = tick
        k = event['kind']
        values = {'kind': k, 'tick': tick}
        if k == 'watchpoint_write':
            for key in ('address', 'pc', 'after'):
                values[key] = _uint(event.get(key), f'event {index}.{key}')
            values['width'] = _uint(event.get('width'), f'event {index}.width')
            if values['width'] not in (1, 2, 4):
                raise ValueError('watchpoint width must be 1, 2 or 4')
        elif k == 'transfer_call':
            for key in ('pc', 'target', 'a0', 'a1', 'a2'):
                values[key] = _uint(event.get(key), f'event {index}.{key}')
        elif k == 'disc_read':
            values['lba'] = _uint(event.get('lba'), f'event {index}.lba')
            values['sectors'] = _uint(event.get('sectors'), f'event {index}.sectors')
            if not 1 <= values['sectors'] <= 2048:
                raise ValueError('disc_read sector count outside bound')
        elif k == 'ram_snapshot':
            values['pc'] = _uint(event.get('pc'), f'event {index}.pc')
        normalized.append(values)

    transfers = [v for v in normalized if v['kind'] == 'transfer_call' and
                 v['target'] == TRANSFER_TARGET and v['a1'] == buffer and v['a2'] == count]
    snapshots = [v for v in normalized if v['kind'] == 'ram_snapshot']
    if len(transfers) != 1 or len(snapshots) != 1:
        raise ValueError('require exactly one matching transfer call and exactly one RAM checkpoint')
    transfer = transfers[0]
    snapshot = snapshots[0]
    if snapshot['tick'] <= transfer['tick']:
        raise ValueError('RAM snapshot must occur after the selected transfer call')
    # An overlapping 1- or 2-byte write invalidates the value witnessed by a
    # previous full-width write; consider ALL overlapping events before call.
    prior_writes = [v for v in normalized if v['kind'] == 'watchpoint_write' and
                    v['tick'] < transfer['tick'] and
                    v['address'] < SLOT + 4 and SLOT < v['address'] + v['width']]
    latest_write = prior_writes[-1] if prior_writes else None
    observed_source = (latest_write if latest_write and latest_write['address'] == SLOT
                       and latest_write['width'] == 4 else None)
    source_matches_a0 = bool(observed_source and observed_source['after'] == transfer['a0'] and
                             _ps1_ram_pointer(transfer['a0']))
    disc_events = [v for v in normalized if v['kind'] == 'disc_read' and
                   v['tick'] < snapshot['tick'] and
                   v['lba'] < cdflr_lba + cdflr_sectors and
                   cdflr_lba < v['lba'] + v['sectors']]

    compare = compare_private_ram(container, raw_ram, address=buffer,
                                  compare_bytes=count, container_offset=0)
    bytes_equal = compare['comparison_status'] == 'EXACT_MATCH'
    return {
        'schema': 1,
        'kind': 'PRIVATE_PS1_RUNTIME_CORRELATION_AUDIT',
        'trace_name': trace_file.name,
        'source_name': Path(container).name,
        'snapshot_name': Path(raw_ram).name,
        'selected_transfer_tick': transfer['tick'],
        'selected_snapshot_tick': snapshot['tick'],
        'latest_matching_watchpoint_tick': observed_source['tick'] if observed_source else None,
        'source_slot_write_agrees_with_a0': source_matches_a0,
        'candidate_cdflr_range_read_count_before_snapshot': len(disc_events),
        'candidate_cdflr_range_read_ticks': [v['tick'] for v in disc_events],
        'byte_comparison': compare,
        'correlation_status': (
            'TRACE_AND_BYTES_CORRELATED' if bytes_equal and source_matches_a0 and disc_events
            else 'PARTIAL_OR_CONTRADICTORY_EVIDENCE'
        ),
        'interpretation': {
            'trace_is_user_supplied_not_independently_authenticated': True,
            'disc_lba_overlap_does_not_prove_payload_causality': True,
            'event_order_does_not_prove_transfer_completed': True,
            'named_resource_origin_not_proven_by_correlation_alone': True,
            'no_original_ram_or_container_bytes_emitted': True,
        },
    }


def _number(text):
    return int(text, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path, help='private debugger JSON event log')
    parser.add_argument('container', type=Path, help='private original CDFLR.BIN')
    parser.add_argument('ram', type=Path, help='private genuine raw 2MiB PS1 RAM dump')
    parser.add_argument('--buffer', type=_number, default=BUFFER)
    parser.add_argument('--bytes', type=_number, default=BUFFER_BYTES)
    args = parser.parse_args()
    result = audit_capture(args.trace, args.container, args.ram,
                           buffer=args.buffer, count=args.bytes)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
