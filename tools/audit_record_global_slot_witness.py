"""Bind private PS1 global pointer LW value claims to the exact EXE slot.

All memory words and register snapshots are USER-SUPPLIED claims, never
independently authenticated PlayStation runtime observations.
"""
import argparse
import json
from pathlib import Path

try:
    from .audit_record_pipeline_coupling import (
        analyze as analyze_joined, MAX_CLAIMS,
        read_raw_iso_entry, MAX_REFERENCE_BYTES,
    )
    from .audit_record_executed_access_claims import _read_site_words, _SITES
    from .audit_record_address_deltas import _address
except ImportError:
    from audit_record_pipeline_coupling import (
        analyze as analyze_joined, MAX_CLAIMS,
        read_raw_iso_entry, MAX_REFERENCE_BYTES,
    )
    from audit_record_executed_access_claims import _read_site_words, _SITES
    from audit_record_address_deltas import _address

SCHEMA = 'wild-arms-ps1-global-slot-witness-claims-v1'
REPORT_SCHEMA = 'wild-arms-ps1-global-slot-witness-audit-v1'
_U32 = 0xffffffff


def _global_slot_opcode_address(words):
    """Compute the global slot address strictly from LUI v1 / LW v1.

    Does not accept a supplied absolute pointer, physical alias or
    unverified register substitution as evidence of the source.
    """
    if len(words) < 11:
        raise ValueError('truncated global pointer signature')
    lui, lw = words[8:10]
    if (lui >> 26 != 15 or (lui >> 21) & 31 != 0
            or (lui >> 16) & 31 != 3
            or lw >> 26 != 35 or (lw >> 21) & 31 != 3
            or (lw >> 16) & 31 != 3):
        raise ValueError('unsupported global pointer source instructions')
    base = (lui & 65535) << 16
    signed_disp = ((lw & 65535) ^ 32768) - 32768
    address = base + signed_disp
    if not 0 <= address <= _U32 or address & 3:
        raise ValueError('invalid derived global pointer slot')
    return base, address


def analyze(exe, reference):
    """Join the previous strict trace with an extra claimed memory witness.

    Each witness covers one exact (site,index) and includes the register
    base before the global LW, its effective address, its PC, and the
    claimed word stored in that global slot. All must agree with the
    ORIGINAL EXE instructions and with the earlier joined observation.
    """
    if (type(reference) is not dict or set(reference) != {
            'schema', 'joined_claim', 'slot_witnesses'}
            or reference['schema'] != SCHEMA):
        raise ValueError('invalid slot witness schema')
    joined = reference['joined_claim']
    witnesses = reference['slot_witnesses']
    if (type(witnesses) is not list
            or not 6 <= len(witnesses) <= MAX_CLAIMS):
        raise ValueError('invalid bounded slot witness count')
    # First enforce EXE hash, PC order, field offset, branch path,
    # delayed register values, and all cross-site address relations.
    earlier = analyze_joined(exe, joined)
    access = joined['access_claim']
    pipeline = {(r['site'], r['record_index']): r
                for r in joined['pipeline_samples']}
    access_rows = {(g['site'], r['record_index']): r
                   for g in access['observations'] for r in g['samples']}
    if (len(witnesses) != len(pipeline) or
            len(pipeline) != len(access_rows)):
        raise ValueError('missing global-slot witness coverage')
    staged = {}
    for w in witnesses:
        if (type(w) is not dict or set(w) != {
                'site', 'record_index', 'global_lw_pc_u32',
                'lui_base_u32', 'effective_slot_address_u32',
                'slot_memory_word_u32'}
                or type(w['site']) is not str
                or type(w['record_index']) is not int):
            raise ValueError('invalid global-slot witness fields')
        key = (w['site'], w['record_index'])
        if key in staged or key not in pipeline or key not in access_rows:
            raise ValueError('duplicate or foreign global-slot witness')
        staged[key] = w

    load = int.from_bytes(exe[0x18:0x1c], 'little')
    size = int.from_bytes(exe[0x1c:0x20], 'little')
    sources = {}
    for site in {site for site, _ in staged}:
        words = _read_site_words(exe, load, size, _SITES[site])
        sources[site] = _global_slot_opcode_address(words)

    matching = 0
    for (site, index), w in staged.items():
        register_base, derived_addr = sources[site]
        sample = pipeline[(site, index)]
        access_row = access_rows[(site, index)]
        supplied_base = _address(w['lui_base_u32'])
        supplied_slot = _address(w['effective_slot_address_u32'])
        supplied_pc = _address(w['global_lw_pc_u32'])
        supplied_value = _address(w['slot_memory_word_u32'])
        loaded = sample['lw_results_u32']
        expected_load_pc = _SITES[site] + 9 * 4
        prior_initial_v1 = sample['initial_gprs_u32'].get('3')
        expected_load_key = f'0x{expected_load_pc:08x}'
        if (supplied_pc == expected_load_pc
                and supplied_base == register_base
                and supplied_slot == derived_addr
                and prior_initial_v1 is not None
                and _address(prior_initial_v1) == register_base
                and expected_load_key in loaded
                and supplied_value == _address(loaded[expected_load_key])
                and supplied_value == _address(access_row['global_base_u32'])):
            matching += 1
    return {
        'schema': REPORT_SCHEMA,
        'unique_exe_global_slot_sources_checked': len(sources),
        'private_site_index_witnesses_checked': len(witnesses),
        'private_slot_witnesses_matching_exe_source': matching,
        'prior_branch_pipeline_claims_consistent':
            earlier['joined_private_claims_consistent'],
        'all_private_global_slot_claims_consistent': bool(
            earlier['joined_private_claims_consistent']
            and matching == len(witnesses)),
        'original_game_slot_memory_independently_observed': False,
        'authentic_ps1_trace_verified': False,
        'hardware_pipeline_cycle_accuracy_verified': False,
        'original_game_record_size_verified': False,
        'nintendo_switch_build_verified': False,
        'private_memory_values_or_addresses_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('private_witnesses', type=Path)
    args = parser.parse_args(argv)
    try:
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        matches = [x for x in entries if type(x) is dict
                   and x.get('path') == '/EXE/WILDARMS.EXE;1'
                   and not x.get('directory', False)]
        if len(matches) != 1:
            raise ValueError('missing private original EXE')
        with args.private_witnesses.open('rb') as stream:
            data = stream.read(MAX_REFERENCE_BYTES + 1)
        if len(data) > MAX_REFERENCE_BYTES:
            raise ValueError('oversized private slot witness')
        result = analyze(read_raw_iso_entry(args.disc, matches[0]),
                         json.loads(data.decode('utf-8')))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_memory_values_or_addresses_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['all_private_global_slot_claims_consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
