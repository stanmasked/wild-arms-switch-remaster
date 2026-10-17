"""Bind privately claimed PS1 executed-PC sequences to a checked EXE image.

The evidence is self-consistency with caller-supplied data. It does NOT
authenticate runtime observations, PS1 hardware, a record size or Switch.
"""
import argparse
import hashlib
import json
import re
from itertools import combinations
from pathlib import Path

try:
    from .verify_record_stride import TARGETS, _static_index_scale, read_raw_iso_entry
    from .audit_record_pointer_use import WINDOW_WORDS, MAX_EXE_BYTES, _POINTER_ADDS
    from .audit_record_base_provenance import _prefix_has_one_instruction_load_gap
    from .audit_record_address_deltas import analyze as analyze_deltas, SCHEMA as DELTA_SCHEMA
    from .audit_record_address_deltas import _address, MIN_SAMPLES
except ImportError:
    from verify_record_stride import TARGETS, _static_index_scale, read_raw_iso_entry
    from audit_record_pointer_use import WINDOW_WORDS, MAX_EXE_BYTES, _POINTER_ADDS
    from audit_record_base_provenance import _prefix_has_one_instruction_load_gap
    from audit_record_address_deltas import analyze as analyze_deltas, SCHEMA as DELTA_SCHEMA
    from audit_record_address_deltas import _address, MIN_SAMPLES

SCHEMA = 'wild-arms-ps1-executed-record-access-claims-v1'
REPORT_SCHEMA = 'wild-arms-ps1-access-claim-correlation-v1'
MAX_REFERENCE_BYTES = 256 * 1024
MAX_SAMPLES_PER_SITE = 32
_SITES = {'site_1': TARGETS[0], 'site_2': TARGETS[1], 'site_3': TARGETS[2]}
_SOURCE = ('synthetic', 'external_ps1_capture_claim')
_HEX_SHA = re.compile(r'[0-9a-f]{64}\Z')
_WIDTH = {32: 1, 33: 2, 35: 4, 36: 1, 37: 2, 40: 1, 41: 2, 43: 4}


def _sign16(word):
    v = word & 0xffff
    return v - 65536 if v & 0x8000 else v


def _candidate_tail(words):
    """Return (access instruction index, signed displacement, width) or None.

    Accept only a *fully linear* path: optional NOPs, one pointer ADDU,
    optional NOPs, then one direct v1-based load/store. Every other opcode,
    including conditional branches and all control delay slots, is refused.
    """
    added = False
    for n in range(11, len(words)):
        word = words[n]
        if word == 0:
            continue
        if word in _POINTER_ADDS and not added:
            added = True
            continue
        op = word >> 26
        if added and op in _WIDTH and (word >> 21) & 31 == 3:
            return n, _sign16(word), _WIDTH[op]
        return None
    return None


def _read_site_words(exe, base, size, site):
    offset = 2048 + site - base
    if offset < 2048 or offset + WINDOW_WORDS * 4 > 2048 + size:
        raise ValueError('unverified EXE site range')
    words = [int.from_bytes(exe[offset + i:offset + i + 4], 'little')
             for i in range(0, WINDOW_WORDS * 4, 4)]
    if _static_index_scale(words[:8], words[8:11]) != 2708:
        raise ValueError('unverified index signature')
    _prefix_has_one_instruction_load_gap(words)
    return words


def analyze(exe, reference):
    """Compare claimed PC order, executable bytes, and address relations.

    Strictly a *claim* correlation: even an exact match cannot demonstrate
    that a genuine debugger emitted the PC sequence or effective addresses.
    """
    if (not isinstance(exe, (bytes, bytearray))
            or len(exe) < 2048 or exe[:8] != b'PS-X EXE'):
        raise ValueError('invalid PS-X EXE')
    load = int.from_bytes(exe[0x18:0x1c], 'little')
    size = int.from_bytes(exe[0x1c:0x20], 'little')
    if not 0 < size <= MAX_EXE_BYTES or 2048 + size > len(exe):
        raise ValueError('invalid bounded EXE payload')
    if (not isinstance(reference, dict) or set(reference) != {
            'schema', 'source', 'exe_sha256', 'observations'}
            or reference.get('schema') != SCHEMA
            or reference.get('source') not in _SOURCE
            or not isinstance(reference.get('exe_sha256'), str)
            or not _HEX_SHA.fullmatch(reference['exe_sha256'])):
        raise ValueError('invalid access claim schema')
    if hashlib.sha256(exe).hexdigest() != reference['exe_sha256']:
        raise ValueError('private executable hash differs')
    groups = reference['observations']
    if not isinstance(groups, list) or not 2 <= len(groups) <= len(TARGETS):
        raise ValueError('invalid independent site count')

    site_names = []
    per_site = []
    all_bases = set()
    addresses_by_site = {}
    claim_pc_matches = 0
    total_claims = 0
    matched_access_shapes = 0
    for group in groups:
        if (not isinstance(group, dict) or set(group) != {
                'site', 'field_offset_s16', 'samples'}
                or type(group.get('site')) is not str
                or group['site'] not in _SITES):
            raise ValueError('invalid access site group')
        name = group['site']
        if name in site_names:
            raise ValueError('duplicate code site')
        site_names.append(name)
        offset = group['field_offset_s16']
        if type(offset) is not int or not -32768 <= offset <= 32767:
            raise ValueError('invalid field displacement')
        rows = group['samples']
        if (not isinstance(rows, list)
                or not MIN_SAMPLES <= len(rows) <= MAX_SAMPLES_PER_SITE):
            raise ValueError('invalid number of site claims')
        words = _read_site_words(exe, load, size, _SITES[name])
        candidate = _candidate_tail(words)
        shape = candidate is not None and candidate[1] == offset
        matched_access_shapes += bool(shape)
        delta_rows = []
        row_by_index = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                    'record_index', 'global_base_u32',
                    'effective_address_u32', 'executed_pcs'}:
                raise ValueError('invalid execution claim fields')
            executed = row['executed_pcs']
            if (not isinstance(executed, list) or
                    not 11 <= len(executed) <= WINDOW_WORDS):
                raise ValueError('invalid claimed instruction sequence')
            pcs = tuple(_address(pc) for pc in executed)
            if len(set(pcs)) != len(pcs):
                raise ValueError('repeated instruction in linear claim')
            index = row['record_index']
            # Stage 235 validates all numeric types and unique indices.
            base = _address(row['global_base_u32'])
            address = _address(row['effective_address_u32'])
            if type(index) is not int or not 0 <= index <= 65535:
                raise ValueError('invalid record index')
            if index in row_by_index:
                raise ValueError('duplicate record index')
            row_by_index[index] = address
            all_bases.add(base)
            delta_rows.append({
                'record_index': index,
                'global_base_u32': row['global_base_u32'],
                'effective_address_u32': row['effective_address_u32']})
            total_claims += 1
            if shape:
                end, _, width = candidate
                expected = tuple(_SITES[name] + 4 * i
                                 for i in range(end + 1))
                if pcs == expected and address % width == 0:
                    claim_pc_matches += 1
        delta_result = analyze_deltas({
            'schema': DELTA_SCHEMA,
            'source': reference['source'],
            'site': name,
            'field_offset_s16': offset,
            'samples': delta_rows})
        per_site.append(delta_result)
        addresses_by_site[name] = (offset, row_by_index)

    common_indices = set.intersection(*(
        set(rows) for _, rows in addresses_by_site.values()))
    if len(common_indices) < MIN_SAMPLES:
        raise ValueError('insufficient overlapping indices across sites')

    checks = matches = 0
    for left, right in combinations(site_names, 2):
        off_left, left_rows = addresses_by_site[left]
        off_right, right_rows = addresses_by_site[right]
        for index in sorted(common_indices):
            checks += 1
            matches += (left_rows[index] - right_rows[index]
                        == off_left - off_right)
    numeric_sites = sum(report['agrees_with_checked_in_opcode_coefficient']
                        for report in per_site)
    stable_all_sites = len(all_bases) == 1
    consistent = bool(
        numeric_sites == len(site_names)
        and stable_all_sites
        and matched_access_shapes == len(site_names)
        and claim_pc_matches == total_claims
        and matches == checks)
    return {
        'schema': REPORT_SCHEMA,
        'matched_ps_x_exe_sha256_claim': True,
        'signature_checked_sites': len(site_names),
        'candidate_linear_memory_access_sites': matched_access_shapes,
        'site_numeric_relationships_matching': numeric_sites,
        'claimed_execution_sequences_matching_static_code': claim_pc_matches,
        'claimed_execution_sequences_checked': total_claims,
        'common_record_indices_across_sites': len(common_indices),
        'cross_site_address_comparisons_matching': matches,
        'cross_site_address_comparisons_checked': checks,
        'claimed_base_constant_across_sites': stable_all_sites,
        'claimed_data_consistent_with_checked_in_code': consistent,
        'claimed_external_capture': reference['source'] == 'external_ps1_capture_claim',
        'actual_runtime_pc_provenance_authenticated': False,
        'original_ps1_hardware_execution_verified': False,
        'original_game_record_size_verified': False,
        'switch_build_verified': False,
        'private_addresses_or_game_bytes_emitted': False,
    }


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
            raise ValueError('invalid inventory')
        with args.private_capture.open('rb') as src:
            data = src.read(MAX_REFERENCE_BYTES + 1)
        if len(data) > MAX_REFERENCE_BYTES:
            raise ValueError('oversized capture claim')
        capture = json.loads(data.decode('utf-8'))
        result = analyze(read_raw_iso_entry(args.disc, found[0]), capture)
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            UnicodeError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_addresses_or_game_bytes_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['claimed_data_consistent_with_checked_in_code'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
