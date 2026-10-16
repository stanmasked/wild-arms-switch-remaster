"""Verify intermediate MIPS arithmetic results against independent private trace.

Private reference is an exact ordered record of successfully executed MIPS
MULT/MULTU, MFHI/MFLO, SRA/SRAV and ADD/ADDU results. A same-value result,
repeated instruction or discarded intermediate result is still an event.
Never emit guest PCs, numeric results or HI/LO values in public reports.
"""

try:
    from .mips_store_event_sequence import u32_word, MAX_MISMATCH_INDICES
except ImportError:
    from mips_store_event_sequence import u32_word, MAX_MISMATCH_INDICES

SCHEMA = 'wild-arms-ps1-arithmetic-events-v1'
MAX_EVENTS = 100000
KINDS = ('mult', 'multu', 'mflo', 'mfhi', 'sra', 'srav', 'add', 'addu')


def instruction_kind(word):
    """Only relevant and valid opcode encodings; other operations are ignored."""
    if type(word) is not int or not 0 <= word <= 0xffffffff:
        raise ValueError('invalid MIPS instruction word')
    if word >> 26 != 0:
        return None
    fn, rs, rt, rd, sa = (word & 63, (word >> 21) & 31,
                           (word >> 16) & 31, (word >> 11) & 31,
                           (word >> 6) & 31)
    if fn in (24, 25) and rd == sa == 0:
        return 'mult' if fn == 24 else 'multu'
    if fn in (16, 18) and rs == rt == sa == 0:
        return 'mfhi' if fn == 16 else 'mflo'
    if fn == 3 and rs == 0:
        return 'sra'
    if fn == 7 and sa == 0:
        return 'srav'
    if fn in (32, 33) and sa == 0:
        return 'add' if fn == 32 else 'addu'
    return None


def executed_event(pc, word, after_regs, hi, lo):
    """Call *only after* a successful MIPS instruction; return private event."""
    kind = instruction_kind(word)
    if kind is None:
        return None
    rd = (word >> 11) & 31
    if kind in ('mult', 'multu'):
        return (pc, kind, lo, hi)
    if not isinstance(after_regs, (tuple, list)) or len(after_regs) != 32:
        raise ValueError('missing arithmetic result registers')
    return (pc, kind, after_regs[rd], None)


def _decode_row(raw):
    if not isinstance(raw, dict) or set(raw) != {
            'pc', 'kind', 'result_u32', 'secondary_u32'}:
        raise ValueError('invalid private arithmetic event shape')
    pc = u32_word(raw['pc'])
    kind = raw['kind']
    if pc & 3 or type(kind) is not str or kind not in KINDS:
        raise ValueError('invalid MIPS arithmetic event PC or kind')
    value = u32_word(raw['result_u32'])
    aux = raw['secondary_u32']
    if kind in ('mult', 'multu'):
        aux = u32_word(aux)
    elif aux is not None:
        raise ValueError('secondary arithmetic result is allowed only for multiplication')
    return (pc, kind, value, aux)


def decode(raw):
    if (not isinstance(raw, dict) or set(raw) != {'schema', 'events'} or
            raw['schema'] != SCHEMA or not isinstance(raw['events'], list) or
            len(raw['events']) > MAX_EVENTS):
        raise ValueError('invalid private arithmetic event reference')
    return tuple(_decode_row(v) for v in raw['events'])


def trace_events(trace):
    """Check private interpreter instrumentation for shape and executed order."""
    if not isinstance(trace, dict):
        raise ValueError('invalid arithmetic execution trace')
    events, visited = trace.get('arithmetic_accesses'), trace.get('visited_pcs')
    if (not isinstance(events, (tuple, list)) or len(events) > MAX_EVENTS or
            not isinstance(visited, (tuple, list))):
        raise ValueError('missing arithmetic or executed-PC trace')
    result = []
    visit_index = 0
    for event in events:
        if (not isinstance(event, (tuple, list)) or len(event) != 4 or
                type(event[0]) is not int or event[0] & 3 or
                not 0 <= event[0] <= 0xffffffff or
                type(event[1]) is not str or event[1] not in KINDS or
                type(event[2]) is not int or not 0 <= event[2] <= 0xffffffff):
            raise ValueError('malformed private arithmetic result event')
        if event[1] in ('mult', 'multu'):
            if type(event[3]) is not int or not 0 <= event[3] <= 0xffffffff:
                raise ValueError('malformed multiplication HI result')
        elif event[3] is not None:
            raise ValueError('unexpected secondary result in arithmetic trace')
        while visit_index < len(visited) and visited[visit_index] != event[0]:
            visit_index += 1
        if visit_index == len(visited):
            raise ValueError('arithmetic event does not match executed guest PC sequence')
        visit_index += 1
        result.append(tuple(event))
    return tuple(result)


def compare(trace, expected, *, guest_stopped_at_expected_pc):
    if type(guest_stopped_at_expected_pc) is not bool:
        raise ValueError('invalid arithmetic stop evidence')
    actual = trace_events(trace)
    if (not isinstance(expected, tuple) or len(expected) > MAX_EVENTS or
            any(not isinstance(e, tuple) or len(e) != 4 for e in expected)):
        raise ValueError('unvalidated arithmetic reference')
    out = {
        'comparison_performed': guest_stopped_at_expected_pc,
        'matches_reference': False,
        'executed_event_count': len(actual),
        'expected_event_count': len(expected),
        'executed_kind_counts': {name: sum(e[1] == name for e in actual)
                                 for name in KINDS},
        'matching_event_count': None,
        'mismatching_event_indices': [],
        'opcode_or_pc_mismatch_indices': [],
        'result_value_mismatch_indices': [],
        'secondary_result_mismatch_indices': [],
        'mismatch_indices_truncated': False,
        'independent_ps1_arithmetic_trace_authenticated': False,
        'private_values_emitted': False,
    }
    if not guest_stopped_at_expected_pc:
        return out
    missing, site_bad, value_bad, aux_bad = [], [], [], []
    for i in range(max(len(actual), len(expected))):
        if i >= len(actual) or i >= len(expected):
            missing.append(i)
        elif actual[i][:2] != expected[i][:2]:
            site_bad.append(i)
        else:
            # LO/primary and HI can differ in the same MULT/MULTU event.
            # Classify both, but count each event only once in the summary.
            if actual[i][2] != expected[i][2]:
                value_bad.append(i)
            if actual[i][3] != expected[i][3]:
                aux_bad.append(i)
    bad = sorted(set(missing + site_bad + value_bad + aux_bad))
    out['matches_reference'] = not bad
    out['matching_event_count'] = max(len(actual), len(expected)) - len(bad)
    out['mismatching_event_indices'] = bad[:MAX_MISMATCH_INDICES]
    out['opcode_or_pc_mismatch_indices'] = site_bad[:MAX_MISMATCH_INDICES]
    out['result_value_mismatch_indices'] = value_bad[:MAX_MISMATCH_INDICES]
    out['secondary_result_mismatch_indices'] = aux_bad[:MAX_MISMATCH_INDICES]
    out['mismatch_indices_truncated'] = any(len(seq) > MAX_MISMATCH_INDICES
                                          for seq in (bad, site_bad, value_bad, aux_bad))
    return out
