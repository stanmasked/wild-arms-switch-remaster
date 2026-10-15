#!/usr/bin/env python3
"""Read-only byte comparison of known repeated CDEF regions on a user-owned PS1 CD.

Only derived counts/offsets are printed; never saves extracted copyrighted bytes.
"""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
PAIRS = [0x1c000, 0x2a000, 0x31000, 0x38000, 0x46000, 0x4d000, 0x54000]
DELTA = 0x4000
REGION = 0x4000
COMMON = 0x3000

def read_entry(image, entry):
    if entry['size'] > 1024 * 1024:
        raise ValueError('audit is limited to 1 MiB ISO files')
    out = bytearray()
    with open(image, 'rb') as stream:
        for sector_index in range((entry['size'] + 2047) // 2048):
            stream.seek((entry['lba'] + sector_index) * 2352)
            sector = stream.read(2352)
            if (len(sector) != 2352 or sector[:12] != SYNC or sector[15] != 2
                    or sector[18] & 0x20 or sector[16:20] != sector[20:24]):
                raise ValueError('not a valid raw MODE2/Form1 sector')
            out.extend(sector[24:2072])
    return bytes(out[:entry['size']])

def compare_pair(data, offset, delta=DELTA, region=REGION, common=COMMON):
    if offset < 0 or delta <= 0 or region <= common or common < 1:
        raise ValueError('invalid pair configuration')
    a, b = data[offset:offset+region], data[offset+delta:offset+delta+region]
    comparable = min(len(a), len(b))
    if comparable < common:
        raise ValueError('not enough bytes for claimed common region')
    first_difference = next((i for i in range(comparable) if a[i] != b[i]), None)
    verified_prefix = comparable if first_difference is None else first_difference
    if verified_prefix < common:
        raise ValueError('known common prefix does not match this image')
    tail_a, tail_b = a[common:], b[common:]
    tail_compared = min(len(tail_a), len(tail_b))
    return {
        'a_offset': f'0x{offset:x}', 'b_offset': f'0x{offset+delta:x}',
        'identical_prefix_bytes': verified_prefix,
        'a_available_bytes': len(a), 'b_available_bytes': len(b),
        'tail_comparable_bytes': tail_compared,
        'tail_different_bytes': sum(x != y for x, y in zip(tail_a, tail_b)),
        'tail_status': 'unavailable' if not tail_compared else
                       ('different' if tail_a[:tail_compared] != tail_b[:tail_compared]
                        else 'identical_in_checked_range'),
        'second_region_truncated': len(b) < region,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', help='User-owned raw 2352-byte BIN')
    parser.add_argument('inventory', help='inspect_disc.py --json output')
    args = parser.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    target = next(e for e in entries if e['path'] == '/BIN/CDEF.BIN;1' and not e['directory'])
    data = read_entry(args.image, target)
    print(json.dumps({'file_size_bytes': len(data),
                      'pairs': [compare_pair(data, x) for x in PAIRS]}, indent=2))

if __name__ == '__main__':
    main()
