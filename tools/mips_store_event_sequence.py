"""Audit executed SB/SH/SW order against a privately supplied debugger log.

The log cannot be recreated from two RAM dumps. This audit compares successful
store PC, resolved address and width, including transient and same-value writes.
Never publish the expected events or concrete guest addresses; public reports
contain only counts and bounded event *indices*. Hardware origin is unverified.
"""

import re


def u32_word(value):
    if type(value) is int and 0 <= value <= 0xffffffff:
        return value
    if isinstance(value, str) and re.fullmatch(r'0[xX][0-9a-fA-F]{1,8}', value):
        return int(value, 16)
    raise ValueError('invalid unsigned 32-bit value')

SCHEMA = 'wild-arms-ps1-store-sequence-v1'
MAX_EVENTS = 100000
MAX_MISMATCH_INDICES = 32
WIDTHS = (1, 2, 4)


def _parse_event(obj):
    if not isinstance(obj, dict) or set(obj) != {'pc', 'address', 'width'}:
        raise ValueError('store record must have pc, address and width')
    pc, address = u32_word(obj['pc']), u32_word(obj['address'])
    width = obj['width']
    if (type(width) is not int or width not in WIDTHS or pc & 3 or
            address % width or address + width > 0x100000000):
        raise ValueError('invalid store record alignment or size')
    return (pc, address, width)


def decode(raw):
    """Strictly validate optional private capture log and preserve order."""
    if (not isinstance(raw, dict) or set(raw) != {'schema', 'events'} or
            raw['schema'] != SCHEMA or not isinstance(raw['events'], list) or
            len(raw['events']) > MAX_EVENTS):
        raise ValueError('invalid store sequence fixture')
    return tuple(_parse_event(event) for event in raw['events'])


def trace_events(trace):
    """Read only successful atomic interpreter events; detect corrupt traces."""
    if not isinstance(trace, dict):
        raise ValueError('invalid store execution trace')
    raw = trace.get('store_accesses')
    addresses = trace.get('store_addresses')
    if (not isinstance(raw, (list, tuple)) or len(raw) > MAX_EVENTS or
            not isinstance(addresses, (list, tuple)) or len(addresses) != len(raw)):
        raise ValueError('missing or mismatched store trace')
    events = []
    for event, address in zip(raw, addresses):
        if (not isinstance(event, (list, tuple)) or len(event) != 4 or
                type(event[3]) is not int or not 0 <= event[3] <= 31):
            raise ValueError('malformed store event')
        pc, resolved, width, _ = event
        if type(pc) is not int or type(resolved) is not int or type(width) is not int:
            raise ValueError('malformed store word')
        if not (0 <= pc <= 0xffffffff and 0 <= resolved <= 0xffffffff and
                pc % 4 == 0 and width in WIDTHS and resolved % width == 0 and
                resolved + width <= 0x100000000 and address == resolved):
            raise ValueError('invalid successful store event')
        events.append((pc, resolved, width))
    return tuple(events)


def compare(trace, expected, *, guest_stopped_at_expected_pc):
    """Compare every completed store including transient writes; privacy-safe."""
    if type(guest_stopped_at_expected_pc) is not bool:
        raise ValueError('invalid stop evidence')
    actual = trace_events(trace)
    if not isinstance(expected, tuple) or any(
            not isinstance(e, tuple) or len(e) != 3 for e in expected):
        raise ValueError('expected validated event sequence')
    widths = {str(width): sum(item[2] == width for item in actual)
              for width in WIDTHS}
    report = {
        'comparison_performed': guest_stopped_at_expected_pc,
        'executed_store_count': len(actual),
        'executed_store_width_counts': widths,
        'expected_store_count': len(expected),
        'matches_reference': False,
        'mismatching_event_indices': [],
        'mismatch_indices_truncated': False,
        'store_sequence_capture_authenticated': False,
        'private_values_emitted': False,
    }
    if not guest_stopped_at_expected_pc:
        return report
    total = max(len(actual), len(expected))
    mismatches = (i for i in range(total) if
                  i >= len(actual) or i >= len(expected) or actual[i] != expected[i])
    all_bad = list(mismatches)
    report['matches_reference'] = not all_bad
    report['mismatching_event_indices'] = all_bad[:MAX_MISMATCH_INDICES]
    report['mismatch_indices_truncated'] = len(all_bad) > MAX_MISMATCH_INDICES
    return report
