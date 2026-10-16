#!/usr/bin/env python3
"""Pack local debugger before/after RAM captures into a private reference JSON.

Only the output JSON contains machine-state values. Never copy it into GitHub,
CI logs or bug reports. Existing outputs are not overwritten.
"""
import argparse
import json
import os
from pathlib import Path

try:
    from .mips_ps1_capture_pack import pack, summarize_capture
    from .mips_ps1_matrix_reference import compare
except ImportError:
    from mips_ps1_capture_pack import pack, summarize_capture
    from mips_ps1_matrix_reference import compare


def _write_private(path, fixture):
    """Create a new 0600 local file, without silently replacing a capture."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(fixture, stream, separators=(',', ':'))
            stream.write('\n')
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--before-registers', type=Path, required=True)
    parser.add_argument('--after-registers', type=Path, required=True)
    parser.add_argument('--before-ram', type=Path, required=True)
    parser.add_argument('--after-ram', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ram-base', default='0x80000000')
    parser.add_argument('--matrix-address', help='default: before $a1 (GPR 5)')
    parser.add_argument('--max-steps', type=int, default=4096)
    parser.add_argument('--synthetic', action='store_true',
                        help='mark capture as synthetic rather than unverified external PS1')
    parser.add_argument('--store-events', type=Path,
                        help='private ordered debugger SB/SH/SW event JSON; not inferred from RAM')
    parser.add_argument('--require-store-sequence', action='store_true',
                        help='require identical executed store PC, address and width order')
    parser.add_argument('--require-final-memory-state', action='store_true',
                        help='verify complete after-RAM blocks including writes outside matrix')
    parser.add_argument('--require-final-cpu-state', action='store_true',
                        help='compare all 32 final GPRs, HI/LO and pending load')
    parser.add_argument('--require-jr-return', action='store_true',
                        help='require completed JR $ra and delay slot at expected stop PC')
    parser.add_argument('--compare', action='store_true',
                        help='also run the stage-211 numerical comparison privately')
    args = parser.parse_args(argv)
    try:
        exe_blob = args.exe.read_bytes()
        fixture = pack(
            exe_blob,
            json.loads(args.before_registers.read_text(encoding='utf-8')),
            json.loads(args.after_registers.read_text(encoding='utf-8')),
            args.before_ram.read_bytes(), args.after_ram.read_bytes(),
            ram_base=args.ram_base,
            matrix_address=args.matrix_address,
            source='synthetic' if args.synthetic else 'external_ps1_capture_claim',
            max_steps=args.max_steps,
            require_completed_jr_ra=args.require_jr_return,
            require_final_cpu_state=args.require_final_cpu_state,
            require_final_memory_state=args.require_final_memory_state,
            store_sequence=(json.loads(args.store_events.read_text(encoding='utf-8'))
                            if args.store_events is not None else None),
            require_store_sequence=args.require_store_sequence)
        result = summarize_capture(fixture)
        # The only printed comparison details are safe counts/slot indices.
        if args.compare:
            verification = compare(exe_blob, fixture)
            result['numerical_comparison_performed'] = bool(verification['coefficient_comparison_performed'])
            result['matching_coefficient_count'] = verification['matching_coefficient_count']
            result['mismatch_slot_indices'] = verification['mismatch_slot_indices']
            result['matches_supplied_nine_coefficients'] = verification['matches_supplied_nine_coefficients']
            result['strict_final_cpu_state_required'] = verification['strict_final_cpu_state_required']
            result['final_cpu_state'] = verification['final_cpu_state']
            result['strict_final_memory_state_required'] = verification['strict_final_memory_state_required']
            result['final_memory_state'] = verification['final_memory_state']
            result['strict_store_sequence_required'] = verification['strict_store_sequence_required']
            result['store_sequence'] = verification['store_sequence']
            result['matches_complete_reference'] = verification['matches_complete_reference']
        _write_private(args.output, fixture)
        print(json.dumps(result, sort_keys=True))
        if args.compare and not result['matches_complete_reference']:
            return 1
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        # Reject privately malformed captures without printing raw exceptions.
        print(json.dumps({'status': 'invalid_capture_or_output',
                          'private_values_emitted': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
