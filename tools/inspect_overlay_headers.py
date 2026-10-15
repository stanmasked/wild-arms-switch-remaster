#!/usr/bin/env python3
"""Read-only structural inspection of PS1 MODE2/Form1 ISO file prefixes."""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

def read_prefix(disc, entry, limit=2048):
    length = min(entry['size'], limit)
    result = bytearray()
    for i in range((length + 2047) // 2048):
        disc.seek((entry['lba'] + i) * 2352)
        s = disc.read(2352)
        if len(s) != 2352 or s[:12] != SYNC:
            raise ValueError(f'Invalid CD sync at LBA {entry["lba"] + i}')
        if s[15] != 2 or s[18] & 0x20:
            raise ValueError('Expected MODE2/Form1 data sector')
        if s[16:20] != s[20:24]:
            raise ValueError('XA subheader mismatch')
        result.extend(s[24:2072])
    return bytes(result[:length])

def analyze_header(payload):
    words = [int.from_bytes(payload[i:i+4], 'little')
             for i in range(0, len(payload)-3, 4)]
    n = 0
    while n < len(words) and 0x80000000 <= words[n] < 0x80200000:
        n += 1
    patterns = {0x27bd0000: 'addiu sp,sp,imm',
                0xafbf0000: 'sw ra,offset(sp)',
                0xafb00000: 'sw s0,offset(sp)',
                0xafb10000: 'sw s1,offset(sp)',
                0xafb20000: 'sw s2,offset(sp)',
                0xafb30000: 'sw s3,offset(sp)'}
    matches = [{'offset': i*4, 'word': f'{words[i]:08x}',
                'pattern': patterns[words[i] & 0xffff0000]}
               for i in range(n, min(n+16, len(words)))
               if (words[i] & 0xffff0000) in patterns]
    return {'initial_address_words': n,
            'initial_addresses_nondecreasing':
                all(words[i] <= words[i+1] for i in range(n-1)),
            'first_non_address_offset': n*4,
            'first_non_address_words': [f'{w:08x}' for w in words[n:n+12]],
            'mips_instruction_candidates': matches}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory', help='Output of inspect_disc.py --json')
    p.add_argument('--paths', nargs='*', help='Exact ISO paths including ;1')
    a = p.parse_args()
    data = json.loads(Path(a.inventory).read_text(encoding='utf-8'))
    selected = set(a.paths) if a.paths else None
    output = []
    with open(a.image, 'rb') as disc:
        for e in data['entries']:
            if e['directory'] or not e['path'].startswith('/BIN/'):
                continue
            if selected is not None and e['path'] not in selected:
                continue
            output.append({'path': e['path'], **analyze_header(read_prefix(disc, e))})
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
