#!/usr/bin/env python3
"""Read-only candidate pointer mapping in duplicated CDEF.BIN regions."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff'*10 + b'\x00'

def read_file(image, entry):
    if not 0 < entry['size'] <= 2000000:
        raise ValueError('file exceeds read-only audit cap')
    result = bytearray()
    with open(image, 'rb') as f:
        for i in range((entry['size'] + 2047)//2048):
            f.seek((entry['lba'] + i)*2352)
            s = f.read(2352)
            if len(s) != 2352 or s[:12] != SYNC:
                raise ValueError('invalid CD sector sync')
            if s[15] != 2 or s[18] & 0x20 or s[16:20] != s[20:24]:
                raise ValueError('expected MODE2/Form1 sector')
            result.extend(s[24:2072])
    return bytes(result[:entry['size']])

def pointer_entries(data, start, base=0x8017c000, count=12, region_size=0x4000):
    if start < 0 or start >= len(data) or count < 1:
        raise ValueError('invalid window')
    region = data[start:start+region_size]
    if len(region) < count*4:
        raise ValueError('truncated pointer table')
    rows = []
    for i in range(count):
        value = int.from_bytes(region[i*4:i*4+4], 'little')
        offset = value - base
        valid = 0 <= offset <= len(region)-4 and not offset % 4
        rows.append({'table_offset': i*4, 'address': f'0x{value:08x}',
                     'mapped_offset': f'0x{offset:x}' if valid else None,
                     'target_first_word': f'0x{int.from_bytes(region[offset:offset+4], "little"):08x}'
                     if valid else None})
    return rows

def compare_mapped(data, start_a=0x38000, start_b=0x3c000, base=0x8017c000, count=12):
    a = pointer_entries(data, start_a, base, count)
    b = pointer_entries(data, start_b, base, count)
    return {'region_a': f'0x{start_a:x}', 'region_b': f'0x{start_b:x}',
            'candidate_base': f'0x{base:08x}',
            'mapped_count': sum(x['mapped_offset'] is not None for x in a),
            'same_pointer_words': all(x['address']==y['address'] for x,y in zip(a,b)),
            'same_target_words': all(x['target_first_word']==y['target_first_word'] for x,y in zip(a,b)),
            'entries': a}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory', help='JSON output of inspect_disc.py --json')
    args = p.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    matches = [e for e in entries if e['path']=='/BIN/CDEF.BIN;1' and not e['directory']]
    if len(matches)!=1:
        p.error('CDEF.BIN not found')
    print(json.dumps(compare_mapped(read_file(args.image, matches[0])), indent=2))

if __name__ == '__main__':
    main()
