#!/usr/bin/env python3
"""Compare a private PS-X EXE replay against a private nine-coefficient reference.

Exit code 0: supplied nine coefficients match and all SHs complete.
Exit code 1: incomplete replay or mismatching coefficients.
Exit code 2: invalid EXE / reference JSON (safe generic error without data).

A matching user-supplied capture is NOT independently verified PS1 hardware.
"""
import argparse
import json
from pathlib import Path

try:
    from .mips_ps1_matrix_reference import compare
except ImportError:
    from mips_ps1_matrix_reference import compare


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True,
                        help='private PS-X EXE; its bytes are never printed')
    parser.add_argument('--reference', type=Path, required=True,
                        help='private JSON with PS1 register/RAM snapshot and nine coefficients')
    args = parser.parse_args(argv)
    try:
        blob = args.exe.read_bytes()
        fixture = json.loads(args.reference.read_text(encoding='utf-8'))
        result = compare(blob, fixture)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        # Never echo the filename, machine-state bytes or an exception with
        # potentially private values. The library raises precise errors for
        # a local developer when invoked directly.
        print(json.dumps({'status':'invalid_reference_or_executable',
                          'private_values_emitted':False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['matches_complete_reference'] else 1


if __name__=='__main__':
    raise SystemExit(main())
