"""Compare bounded synthetic MIPS input probes without publishing game values.

Single-register perturbations are diagnostic observations, not proof of
functional dependence or independence of the original game engine.
"""


def compare_runs(baseline, changed):
    """Only return aggregate control-flow and 9-slot output differences.

    Each private in-memory run is a mapping with 'returned', 'visited',
    'written_offsets', and 'coefficients'. Raw values stay inside this call.
    Coefficient comparison is allowed only for two complete nine-slot returns.
    """
    offsets = frozenset(range(0, 18, 2))
    base_written = set(baseline['written_offsets'])
    changed_written = set(changed['written_offsets'])
    comparable = (bool(baseline['returned']) and bool(changed['returned'])
                  and base_written == offsets and changed_written == offsets
                  and len(baseline['coefficients']) == 9
                  and len(changed['coefficients']) == 9)
    count = (sum(a != b for a, b in zip(baseline['coefficients'],
                                        changed['coefficients']))
             if comparable else None)
    return {
        'both_returned_to_caller': bool(baseline['returned'] and changed['returned']),
        'execution_path_changed': tuple(baseline['visited']) != tuple(changed['visited']),
        'matrix_store_coverage_changed': base_written != changed_written,
        'all_nine_coefficients_comparable': comparable,
        'changed_coefficient_count': count,
    }


def probe_input_registers(run, registers=(4, 6, 7), delta=1):
    """Call run(None, 0) for baseline, run(reg, delta) for variations.

    The callable owns private bytes; only safe numeric counts and booleans
    are exposed. No initial GPR values, table entries or outputs returned.
    """
    if not isinstance(delta, int) or delta == 0 or not -0x80000000 <= delta <= 0xffffffff:
        raise ValueError('delta must be a nonzero 32-bit integer')
    if any(not isinstance(reg, int) or reg not in (4, 6, 7) for reg in registers):
        raise ValueError('only a0, a2, a3 can be probed safely in caller frame')
    if len(set(registers)) != len(registers):
        raise ValueError('duplicate input register')
    baseline = run(None, 0)
    comparisons = []
    for reg in registers:
        variation = run(reg, delta)
        summary = compare_runs(baseline, variation)
        comparisons.append({'gpr': reg, **summary})
    return {'baseline_returned_to_caller': bool(baseline['returned']),
            'tested_register_count': len(comparisons),
            'perturbation_nonzero': True,
            'observations': comparisons,
            'original_gameplay_inputs_known': False}
