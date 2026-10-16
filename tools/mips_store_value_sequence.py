"""Private verification of the exact values written by successful MIPS stores.

The expected ordered trace MUST come from an independent debugger capture,
not from before/after RAM; temporary and same-value stores are observable.
Guest values/addresses/PCs are retained in the private fixture and trace only.
Public summaries disclose bounded event indices and aggregate counts, never
actual values, checksums, source registers or addresses.
"""

from .mips_store_event_sequence import (
    MAX_EVENTS, MAX_MISMATCH_INDICES, WIDTHS, _parse_event, trace_events,
    u32_word,
)

SCHEMA = 'wild-arms-ps1-store-values-v1'


def decode(raw):
    """Validate complete reference, including exact *stored* low bits."""
    if (not isinstance(raw, dict) or set(raw) != {'schema', 'events'} or
            raw['schema'] != SCHEMA or not isinstance(raw['events'], list) or
            len(raw['events']) > MAX_EVENTS):
        raise ValueError('invalid private store-value fixture')
    events = []
    for obj in raw['events']:
        if not isinstance(obj, dict) or set(obj) != {'pc', 'address', 'width', 'value_u32'}:
            raise ValueError('store-value event needs pc, address, width, value_u32')
        pc, addr, width = _parse_event({k: obj[k] for k in ('pc','address','width')})
        value = u32_word(obj['value_u32'])
        if value >= 1 << (8 * width):
            raise ValueError('store-value reference is not truncated to store width')
        events.append((pc, addr, width, value))
    return tuple(events)


def project_sites(reference):
    """Allow comparison with independently supplied address-only events."""
    return tuple(event[:3] for event in reference)


def trace_values(trace):
    """Fail closed if the value trace diverges from successful store events."""
    sites = trace_events(trace)
    values = trace.get('store_value_accesses')
    if not isinstance(values, (list, tuple)) or len(values) != len(sites):
        raise ValueError('missing or inconsistent store-value execution trace')
    result = []
    for record, site in zip(values, sites):
        if (not isinstance(record, (list, tuple)) or len(record) != 5 or
                any(type(v) is not int for v in record) or
                record[:3] != site or
                not 0 <= record[3] <= 31 or
                not 0 <= record[4] < (1 << (8 * site[2]))):
            raise ValueError('invalid successful store-value event')
        # Cross-check old RT field too: both streams attest the same operation.
        # This is private metadata and is omitted from the public report.
        result.append((record[0], record[1], record[2], record[4]))
    for value, old in zip(values, trace['store_accesses']):
        if value[:4] != old:
            raise ValueError('inconsistent source RT in store-value trace')
    return tuple(result)


def compare(trace, expected, *, guest_stopped_at_expected_pc):
    if type(guest_stopped_at_expected_pc) is not bool:
        raise ValueError('invalid store-value stop evidence')
    if (not isinstance(expected, tuple) or len(expected) > MAX_EVENTS or
            any(not isinstance(row, tuple) or len(row) != 4 for row in expected)):
        raise ValueError('expected validated store-value fixture')
    actual = trace_values(trace)
    widths = {str(width):sum(e[2] == width for e in actual) for width in WIDTHS}
    out = {
        'comparison_performed': guest_stopped_at_expected_pc,
        'matches_reference': False,
        'executed_store_count':len(actual),
        'expected_store_count':len(expected),
        'executed_store_width_counts':widths,
        'matching_event_count':None,
        'mismatching_event_indices':[],
        'value_mismatch_event_indices':[],
        'site_mismatch_event_indices':[],
        'mismatch_indices_truncated':False,
        'independent_ps1_trace_authenticated':False,
        'private_values_emitted':False,
    }
    if not guest_stopped_at_expected_pc:
        return out
    missing = []
    value_bad = []
    site_bad = []
    for i in range(max(len(actual),len(expected))):
        if i >= len(actual) or i >= len(expected):
            missing.append(i)
        elif actual[i][:3] != expected[i][:3]:
            site_bad.append(i)
        elif actual[i][3] != expected[i][3]:
            value_bad.append(i)
    bad = sorted(missing + site_bad + value_bad)
    out['matching_event_count'] = max(len(actual),len(expected)) - len(bad)
    out['mismatching_event_indices'] = bad[:MAX_MISMATCH_INDICES]
    out['value_mismatch_event_indices'] = value_bad[:MAX_MISMATCH_INDICES]
    out['site_mismatch_event_indices'] = site_bad[:MAX_MISMATCH_INDICES]
    out['mismatch_indices_truncated'] = (len(bad) > MAX_MISMATCH_INDICES or
                                         len(site_bad) > MAX_MISMATCH_INDICES or
                                         len(value_bad) > MAX_MISMATCH_INDICES)
    out['matches_reference'] = not bad
    return out
