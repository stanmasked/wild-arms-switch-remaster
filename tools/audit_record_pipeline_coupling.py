"""Couple private MIPS branch PC claims to delayed LW value/predicate claims.

Only synthetic/user-provided consistency is checked; no game RAM, debugger
authenticity, PS1 hardware cycle accuracy, record size, or Switch build.
"""
import argparse
import json
from pathlib import Path

try:
    from .audit_record_branch_access_claims import analyze as analyze_branches
    from .audit_record_executed_access_claims import (
        _read_site_words, _SITES, MAX_REFERENCE_BYTES, read_raw_iso_entry,
    )
    from .audit_record_address_deltas import _address
    from .audit_mips_load_delay_predicates import analyze as analyze_pipeline
except ImportError:
    from audit_record_branch_access_claims import analyze as analyze_branches
    from audit_record_executed_access_claims import (
        _read_site_words, _SITES, MAX_REFERENCE_BYTES, read_raw_iso_entry,
    )
    from audit_record_address_deltas import _address
    from audit_mips_load_delay_predicates import analyze as analyze_pipeline

SCHEMA = 'wild-arms-ps1-coupled-branch-load-claims-v1'
REPORT_SCHEMA = 'wild-arms-ps1-coupled-branch-load-report-v1'
MAX_CLAIMS = 96
_U32 = 0xffffffff


def _sign16(word):
    value = word & 65535
    return value - 65536 if value & 32768 else value


def analyze(exe, reference):
    """Fail closed when the same reported PCs cannot satisfy both oracles.

    Stage 237 checks exact EXE hash/opcodes/PCs and cross-site addresses.
    Stage 238 then independently evaluates the claimed initial GPRs,
    supplied LW values, pending writes and BEQ/BNE predicates for the
    identical suffix (from the prefix's global LW to the final LW).
    """
    if (type(reference) is not dict or set(reference) != {
            'schema', 'access_claim', 'pipeline_samples'}
            or reference.get('schema') != SCHEMA):
        raise ValueError('invalid joined claim schema')
    access = reference['access_claim']
    samples = reference['pipeline_samples']
    if type(samples) is not list or not 6 <= len(samples) <= MAX_CLAIMS:
        raise ValueError('invalid bounded pipeline sample count')

    stage237 = analyze_branches(exe, access)
    wanted = {}
    for group in access['observations']:
        for row in group['samples']:
            key = (group['site'], row['record_index'])
            if key in wanted:
                raise ValueError('duplicate indexed access claim')
            wanted[key] = row
    if len(wanted) != len(samples):
        raise ValueError('incomplete joined site/index coverage')

    staged = {}
    for item in samples:
        if (type(item) is not dict or set(item) != {
                'site', 'record_index', 'initial_gprs_u32', 'lw_results_u32'}
                or type(item['site']) is not str
                or type(item['record_index']) is not int
                or type(item['initial_gprs_u32']) is not dict
                or type(item['lw_results_u32']) is not dict):
            raise ValueError('invalid joined pipeline fields')
        key = (item['site'], item['record_index'])
        if key in staged or key not in wanted:
            raise ValueError('duplicate or foreign pipeline site/index')
        staged[key] = item

    load = int.from_bytes(exe[0x18:0x1c], 'little')
    size = int.from_bytes(exe[0x1c:0x20], 'little')
    matching = 0
    total_branches = 0
    total_loads = 0
    for (site, index), row in wanted.items():
        entry = staged[(site, index)]
        registers = entry['initial_gprs_u32']
        load_results = entry['lw_results_u32']
        if (len(load_results) > 4 or
                any(type(k) is not str for k in load_results)):
            raise ValueError('invalid bounded LW results')
        words = _read_site_words(exe, load, size, _SITES[site])
        pcs = tuple(_address(pc) for pc in row['executed_pcs'])
        if (len(pcs) < 13 or pcs[9] != _SITES[site] + 36
                or pcs[10] != _SITES[site] + 40
                or (words[9] >> 26) != 35
                or (words[10] != 0x00021080)):
            raise ValueError('unverified load gap in claimed EXE path')
        if any(pc < _SITES[site] or pc >= _SITES[site] + 84
               or (pc - _SITES[site]) & 3 for pc in pcs):
            # The stage-237 syntactic PC claim already fails. Do not
            # reinterpret a foreign PC as a negative Python array index.
            continue
        expected_lws = {
            pc for pc in pcs[9:]
            if (words[(pc - _SITES[site]) // 4] >> 26) == 35
        }
        # This intentionally allows only the original global LW and one
        # terminal LW, not extra loads or branch-slot memory operations.
        if (len(expected_lws) != 2
                or set(load_results) != {
                    f'0x{pc:08x}' for pc in expected_lws}
                or any(_address(pc) != pc_value
                       for pc, pc_value in zip(
                           sorted(load_results), sorted(expected_lws)))):
            raise ValueError('unexpected private LW capture shape')
        if (registers.get('2') != f'0x{677 * index & _U32:08x}'
                or _address(load_results[f'0x{pcs[9]:08x}'])
                != _address(row['global_base_u32'])):
            # A structurally valid but inconsistent index/base claim.
            continue
        steps = []
        for n, pc in enumerate(pcs[9:], start=9):
            slot = (pc - _SITES[site]) // 4
            word = words[slot]
            trace = {'pc_u32': f'0x{pc:08x}', 'word_u32': f'0x{word:08x}'}
            if word >> 26 == 35:
                trace['load_result_u32'] = load_results[f'0x{pc:08x}']
            if word >> 26 in (4, 5):
                if n + 2 >= len(pcs):
                    raise ValueError('branch without claimed successor')
                target = pc + 4 + _sign16(word) * 4
                fallthrough = pc + 8
                if target == fallthrough:
                    raise ValueError('ambiguous taken versus fallthrough branch')
                successor = pcs[n + 2]
                if successor not in (target, fallthrough):
                    raise ValueError('unverified claimed branch successor')
                trace['claimed_taken'] = successor == target
            steps.append(trace)
        model_claim = {
            'schema': 'wild-arms-ps1-load-delay-predicate-claims-v1',
            'source': access['source'],
            'initial_gprs_u32': registers,
            'steps': steps,
        }
        try:
            result = analyze_pipeline(
                model_claim,
                expected_final_lw_access_u32=_address(
                    row['effective_address_u32']))
        except (ValueError, TypeError, KeyError, IndexError):
            # A self-consistent EXE path can still contradict the claimed
            # loaded register values or predicate, without leaking either.
            continue
        matching += 1
        total_branches += result['claimed_beq_bne_predicates_checked']
        total_loads += result['claimed_lw_results_consumed']

    agree = bool(stage237['claimed_data_consistent_with_checked_in_code']
                 and matching == len(samples))
    return {
        'schema': REPORT_SCHEMA,
        'sites_checked': stage237['signature_checked_sites'],
        'joined_site_index_samples_checked': len(samples),
        'joint_branch_load_samples_matching': matching,
        'claimed_branch_predicates_matching': total_branches,
        'claimed_lw_values_bound_to_exe_opcodes': total_loads,
        'stage237_exe_address_claims_consistent':
            stage237['claimed_data_consistent_with_checked_in_code'],
        'joined_private_claims_consistent': agree,
        'original_ps1_trace_authenticated': False,
        'hardware_cycle_accurate_pipeline_verified': False,
        'original_game_record_size_verified': False,
        'native_switch_build_verified': False,
        'private_data_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('joined_private_claim', type=Path)
    args = parser.parse_args(argv)
    try:
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        found = [r for r in entries if isinstance(r, dict)
                 and r.get('path') == '/EXE/WILDARMS.EXE;1'
                 and not r.get('directory', False)]
        if len(found) != 1:
            raise ValueError('private EXE inventory mismatch')
        with args.joined_private_claim.open('rb') as file:
            raw = file.read(MAX_REFERENCE_BYTES + 1)
        if len(raw) > MAX_REFERENCE_BYTES:
            raise ValueError('oversized private joined claim')
        result = analyze(read_raw_iso_entry(args.disc, found[0]),
                         json.loads(raw.decode('utf-8')))
    except (OSError, ValueError, TypeError, KeyError,
            IndexError, UnicodeError, OverflowError, RecursionError):
        print(json.dumps({'schema': REPORT_SCHEMA, 'valid_input': False,
                          'error_code': 'invalid_private_input',
                          'private_data_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['joined_private_claims_consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
