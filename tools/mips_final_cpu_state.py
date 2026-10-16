"""Private, full-register PS1 debugger final-state comparison.

The expected state may only be asserted by the supplied debugger export.  The
report exposes mismatch GPR *indices* and aggregate HI/LO/pipeline booleans,
never numerical registers or the loaded value.  This is not PS1 authenticity.
"""
import re


def word(value):
    if type(value) is int and 0 <= value <= 0xffffffff:
        return value
    if isinstance(value, str) and re.fullmatch(r'0[xX][0-9a-fA-F]{1,8}', value):
        return int(value, 16)
    raise ValueError('invalid captured 32-bit machine word')


def decode_expected(raw):
    """Validate a complete post-instruction state; never fill gaps with zeros."""
    if not isinstance(raw, dict) or set(raw) != {
            'gpr', 'hi', 'lo', 'pending_load', 'in_branch_delay_slot'}:
        raise ValueError('post-return state must contain complete CPU fields')
    gpr = raw['gpr']
    if not isinstance(gpr, list) or len(gpr) != 32:
        raise ValueError('expected 32 final GPR values')
    values = tuple(word(v) for v in gpr)
    if values[0] != 0:
        raise ValueError('final r0 must equal zero')
    slot = raw['in_branch_delay_slot']
    if type(slot) is not bool or slot:
        raise ValueError('unsupported post-return branch delay slot')
    pending = raw['pending_load']
    if pending is not None:
        if not isinstance(pending, dict) or set(pending) != {'gpr', 'value_u32'}:
            raise ValueError('malformed final pending load')
        destination = pending['gpr']
        if type(destination) is not int or not 1 <= destination <= 31:
            raise ValueError('invalid final pending load destination')
        pending = (destination, word(pending['value_u32']))
    return {'gpr': values, 'hi': word(raw['hi']), 'lo': word(raw['lo']),
            'pending_load': pending}


def compare(trace, expected, *, guest_stopped_at_expected_pc):
    """Compare validated expected post-PC values to interpreter's last state."""
    if not isinstance(trace, dict) or not isinstance(expected, dict):
        raise ValueError('invalid final state inputs')
    if type(guest_stopped_at_expected_pc) is not bool:
        raise ValueError('invalid stop boundary evidence')
    if (not isinstance(trace.get('gpr'), (list, tuple)) or
            len(trace['gpr']) != 32):
        raise ValueError('missing final MIPS register state')
    actual_gpr = trace['gpr']
    if any(type(v) is not int or not 0 <= v <= 0xffffffff for v in actual_gpr):
        raise ValueError('invalid result GPR')
    if type(trace.get('hi')) is not int or type(trace.get('lo')) is not int:
        raise ValueError('missing final HI/LO')
    actual_pending = trace.get('pending_load')
    if actual_pending is not None:
        if (not isinstance(actual_pending, (list, tuple)) or len(actual_pending) != 2 or
                type(actual_pending[0]) is not int or
                type(actual_pending[1]) is not int):
            raise ValueError('malformed final pipeline state')
        actual_pending = tuple(actual_pending)
    matched_gprs = ()
    hi_match = lo_match = pipeline_match = None
    if guest_stopped_at_expected_pc:
        matched_gprs = tuple(i for i,(a,b) in enumerate(zip(actual_gpr,expected['gpr']))
                             if a != b)
        hi_match = trace['hi'] == expected['hi']
        lo_match = trace['lo'] == expected['lo']
        pipeline_match = actual_pending == expected['pending_load']
    success = bool(guest_stopped_at_expected_pc and not matched_gprs and
                   hi_match and lo_match and pipeline_match)
    return {
        'final_cpu_state_comparison_performed': guest_stopped_at_expected_pc,
        'final_cpu_state_matches_reference': success,
        'mismatching_gpr_indices': list(matched_gprs) if guest_stopped_at_expected_pc else [],
        'matching_gpr_count': 32-len(matched_gprs) if guest_stopped_at_expected_pc else None,
        'hi_matches_reference': hi_match,
        'lo_matches_reference': lo_match,
        'pending_load_matches_reference': pipeline_match,
        'actual_ps1_hardware_state_authenticated': False,
        'private_values_emitted': False,
    }
