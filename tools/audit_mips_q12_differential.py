#!/usr/bin/env python3
"""Reproducible independent-oracle checks of synthetic MIPS Q12 matrix math.

No private game assets, real game coefficients, external tools or random
nondeterminism. Summaries do not print operand arrays or guest memory values.
"""
import argparse
import json
import random

from .mips_q12_differential import (
    build_nine_product_program, build_nine_dot3_program, replay,
    reference_product_outputs, reference_dot3_outputs,
)

EDGES = (0, 1, 2, 4095, 4096, 4097, 32767, 32768, 65535,
         0xf000, 0xe000, 0x8001)


def audit(*, cases=128, seed=206):
    """Compare three precise integer schedules, return safe aggregate status."""
    if not isinstance(cases, int) or not 1 <= cases <= 10000:
        raise ValueError('cases must be 1..10000')
    if not isinstance(seed, int) or not 0 <= seed <= 0xffffffff:
        raise ValueError('seed must be an unsigned 32-bit integer')
    random_source = random.Random(seed)
    patterns = (
        ('single_product', 9, build_nine_product_program(),
         reference_product_outputs),
        ('dot3_shift_after_sum', 27, build_nine_dot3_program(),
         reference_dot3_outputs),
        ('dot3_shift_each_product', 27,
         build_nine_dot3_program(shift_each=True),
         lambda a,b: reference_dot3_outputs(a,b,shift_each=True)),
    )
    counts = {}
    for label, count, code, reference in patterns:
        for case in range(cases):
            if case % 2 == 0:
                left = [random_source.choice(EDGES) for _ in range(count)]
                right = [random_source.choice(EDGES) for _ in range(count)]
            else:
                left = [random_source.getrandbits(16) for _ in range(count)]
                right = [random_source.getrandbits(16) for _ in range(count)]
            actual = replay(code, left, right)
            expected = reference(left, right)
            if actual != expected:
                raise AssertionError('synthetic differential mismatch in %s case %d'
                                     % (label, case))
        counts[label] = cases
    return {
        'synthetic_comparisons_passed': sum(counts.values()),
        'cases_per_schedule': cases,
        'schedules': counts,
        'deterministic_seed_used': True,
        'signed_multiply_and_sh_truncation_checked': True,
        'shift_placement_variants_checked': True,
        'original_gameplay_coefficients_checked': False,
        'playstation_hardware_equivalence_proven': False,
        'game_assets_emitted': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=int, default=128)
    parser.add_argument('--seed', type=int, default=206)
    args = parser.parse_args()
    print(json.dumps(audit(cases=args.cases, seed=args.seed), indent=2))


if __name__ == '__main__':
    main()
