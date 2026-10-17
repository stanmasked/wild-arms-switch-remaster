"""Privacy-safe comparison of privately supplied PS1 index/address observations.

A matching numerical relation is NOT an authenticated hardware capture,
nor proof of the original game's record size, branch path, or base pointer.
"""
import argparse
import json
import re
from itertools import combinations
from pathlib import Path

try:
    from .verify_record_stride import INDEX_WORDS, GLOBAL_WORDS, _static_index_scale
except ImportError:
    from verify_record_stride import INDEX_WORDS, GLOBAL_WORDS, _static_index_scale

SCHEMA = 'wild-arms-ps1-index-address-observations-v1'
REPORT_SCHEMA = 'wild-arms-ps1-index-address-delta-audit-v1'
MIN_SAMPLES = 3
MAX_SAMPLES = 128
MAX_REFERENCE_BYTES = 64 * 1024
_MAX_U32 = 0xffffffff
_SOURCES = ('synthetic', 'external_ps1_capture_claim')
_SITES = ('site_1', 'site_2', 'site_3')
_ADDRESS = re.compile(r'0[xX][0-9a-fA-F]{8}\Z')


def _address(value):
    if not isinstance(value, str) or _ADDRESS.fullmatch(value) is None:
        raise ValueError('invalid private unsigned address')
    return int(value, 16)


def analyze(reference):
    """Check independent address and pairwise-difference relations.

    Only one claimed global base, one indexed code site, and one field
    offset can be compared in one report. This avoids combining two
    allocations, field accesses, or independent functions as one stride.
    """
    if (not isinstance(reference, dict) or set(reference) != {
            'schema', 'source', 'site', 'field_offset_s16', 'samples'}
            or reference['schema'] != SCHEMA
            or reference['source'] not in _SOURCES
            or reference['site'] not in _SITES):
        raise ValueError('invalid observation schema')
    offset = reference['field_offset_s16']
    if type(offset) is not int or not -32768 <= offset <= 32767:
        raise ValueError('invalid signed field displacement')
    rows = reference['samples']
    if (not isinstance(rows, list) or
            not MIN_SAMPLES <= len(rows) <= MAX_SAMPLES):
        raise ValueError('invalid number of observations')

    samples = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
                'record_index', 'global_base_u32', 'effective_address_u32'}:
            raise ValueError('invalid observation fields')
        index = row['record_index']
        if type(index) is not int or not 0 <= index <= 65535:
            raise ValueError('invalid unsigned record index')
        samples.append((index, _address(row['global_base_u32']),
                        _address(row['effective_address_u32'])))
    samples.sort(key=lambda row: row[0])
    if len({row[0] for row in samples}) != len(samples):
        raise ValueError('duplicate record index')

    scale = _static_index_scale(INDEX_WORDS, GLOBAL_WORDS)
    first_base = samples[0][1]
    stable_base = all(base == first_base for _, base, _ in samples)
    valid_no_wrap = all(
        0 <= base + index * scale + offset <= _MAX_U32
        for index, base, _ in samples)
    candidate_matches = sum(
        0 <= base + index * scale + offset <= _MAX_U32
        and effective == base + index * scale + offset
        for index, base, effective in samples)
    pair_checks = 0
    pair_matches = 0
    for (ix0, _, address0), (ix1, _, address1) in combinations(samples, 2):
        pair_checks += 1
        pair_matches += (address1 - address0) == (ix1 - ix0) * scale
    agrees = bool(stable_base and valid_no_wrap and
                  candidate_matches == len(samples) and
                  pair_matches == pair_checks)

    return {
        'schema': REPORT_SCHEMA,
        'claimed_external_capture': reference['source'] == 'external_ps1_capture_claim',
        'observations_checked': len(samples),
        'independent_index_pairs_checked': pair_checks,
        'candidate_address_matches': candidate_matches,
        'index_delta_pairs_matching_opcode_coefficient': pair_matches,
        'claimed_global_base_constant': stable_base,
        'no_32bit_address_wrap_required': valid_no_wrap,
        'agrees_with_checked_in_opcode_coefficient': agrees,
        'checked_in_opcode_coefficient': scale,
        'authentic_ps1_capture_independently_verified': False,
        'original_executable_signature_checked': False,
        'runtime_memory_access_verified': False,
        'record_size_verified': False,
        'native_switch_build_verified': False,
        'private_addresses_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_observations', type=Path,
                        help='Private JSON observations; never upload to GitHub')
    args = parser.parse_args(argv)
    try:
        with args.private_observations.open('rb') as stream:
            raw = stream.read(MAX_REFERENCE_BYTES + 1)
        if len(raw) > MAX_REFERENCE_BYTES:
            raise ValueError('oversized observation input')
        reference = json.loads(raw.decode('utf-8'))
        result = analyze(reference)
    except (OSError, ValueError, UnicodeError, TypeError,
            KeyError, OverflowError, RecursionError):
        # Never reveal private filename, address value, or parser exception.
        print(json.dumps({'schema': REPORT_SCHEMA, 'valid_input': False,
                          'error_code': 'invalid_private_input',
                          'private_addresses_emitted': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['agrees_with_checked_in_opcode_coefficient'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
