"""Aggregate privacy-safe claims for bounded BEQ/BNE PS1 PC sequences.

This verifies supplied data against the static EXE; it never authenticates
actual PS1 execution or asserts a genuine in-game structure size.
"""
import argparse
import json
from pathlib import Path

try:
    from .audit_record_executed_access_claims import (
        analyze as analyze_claims, MAX_REFERENCE_BYTES, read_raw_iso_entry,
    )
    from .mips_record_branch_trace import validate
except ImportError:
    from audit_record_executed_access_claims import (
        analyze as analyze_claims, MAX_REFERENCE_BYTES, read_raw_iso_entry,
    )
    from mips_record_branch_trace import validate

SCHEMA = 'wild-arms-ps1-branch-access-claim-correlation-v1'


def analyze(exe, claim):
    total_slots = 0
    unknown_predicates = 0

    def check(words, start, pcs, offset, address):
        nonlocal total_slots, unknown_predicates
        outcome = validate(words, start, pcs, offset, address)
        if outcome is not None:
            total_slots += outcome['validated_branch_slots']
            unknown_predicates += outcome['unknown_branch_predicates']
        return outcome

    report = analyze_claims(exe, claim, path_validator=check)
    report['schema'] = SCHEMA
    report['candidate_delay_aware_memory_access_sites'] = report.pop(
        'candidate_linear_memory_access_sites')
    report['claimed_nop_delay_slots_validated'] = total_slots
    report['claimed_unknown_branch_predicates'] = unknown_predicates
    report['supports_beq_bne_forward_with_nop_slot_only'] = True
    report['observed_branch_predicate_authenticated'] = False
    report['hardware_cycle_accurate_load_delay_verified'] = False
    report['runtime_instruction_provenance_verified'] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('private_capture', type=Path)
    args = parser.parse_args(argv)
    try:
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        found = [x for x in entries if isinstance(x, dict)
                 and x.get('path') == '/EXE/WILDARMS.EXE;1'
                 and not x.get('directory', False)]
        if len(found) != 1:
            raise ValueError('invalid private inventory')
        with args.private_capture.open('rb') as f:
            data = f.read(MAX_REFERENCE_BYTES + 1)
        if len(data) > MAX_REFERENCE_BYTES:
            raise ValueError('oversized capture claim')
        claim = json.loads(data.decode('utf-8'))
        report = analyze(read_raw_iso_entry(args.disc, found[0]), claim)
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            UnicodeError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_addresses_or_game_bytes_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report['claimed_data_consistent_with_checked_in_code'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
