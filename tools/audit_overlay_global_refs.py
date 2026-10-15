#!/usr/bin/env python3
"""Read-only cross-file audit of adjacent MIPS global-pointer references.

Never emits copyrighted executable bytes. Large BIN files are sampled by prefix.
"""
import argparse
import json
from pathlib import Path

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
OP_LOAD = {32, 33, 34, 35, 36, 37, 38}
OP_STORE = {40, 41, 42, 43, 46}
DEFAULT_TARGET = 0x800d2c3c

def read_prefix(disc, entry, cap):
    length = min(entry['size'], cap)
    chunks = []
    for i in range((length + 2047) // 2048):
        disc.seek((entry['lba'] + i) * 2352)
        sector = disc.read(2352)
        if len(sector) != 2352 or sector[:12] != SYNC:
            raise ValueError(f'bad sync in {entry["path"]} at sector {i}')
        if sector[15] != 2 or sector[18] & 0x20 or sector[16:20] != sector[20:24]:
            raise ValueError(f'not MODE2/Form1 in {entry["path"]} at sector {i}')
        chunks.append(sector[24:2072])
    return b''.join(chunks)[:length]

def scan_pairs(payload, address=DEFAULT_TARGET):
    upper = ((address >> 16) + (1 if address & 0x8000 else 0)) & 0xffff
    lower = address & 0xffff
    hits = []
    words = [int.from_bytes(payload[i:i+4], 'little')
             for i in range(0, len(payload) - 3, 4)]
    for i in range(len(words)-1):
        a, b = words[i:i+2]
        register = (a >> 16) & 31
        op = b >> 26
        if (a >> 26 == 15 and register != 0 and (a & 0xffff) == upper
            and ((b >> 21) & 31) == register and (b & 0xffff) == lower
            and op in OP_LOAD | OP_STORE):
            hits.append({'offset': 4*i, 'kind': 'store' if op in OP_STORE else 'load'})
    return hits

def common_prefix(a, b):
    for n, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return n
    return min(len(a), len(b))

def audit(image, entries, address=DEFAULT_TARGET, cap=1024*1024):
    if not 2048 <= cap <= 32*1024*1024:
        raise ValueError('cap out of bounds')
    output = []
    with open(image, 'rb') as disc:
        for entry in entries:
            if entry['directory'] or not entry['path'].startswith(('/EXE/', '/BIN/')):
                continue
            sample = read_prefix(disc, entry, max(cap,entry['size']) if
                                 entry['path'].startswith('/EXE/') else cap)
            # EXE code begins after its 2048-byte PS-X EXE header.
            executable = entry['path'].startswith('/EXE/') and sample[:8] == b'PS-X EXE'
            data = sample[2048:] if executable else sample
            hits = scan_pairs(data, address)
            output.append({
                'path': entry['path'], 'bytes_examined': len(data),
                'complete_file_examined': len(sample) == entry['size'],
                'offset_origin': 'after_psx_exe_header' if executable else 'file_start',
                'loads': sum(h['kind'] == 'load' for h in hits),
                'stores': sum(h['kind'] == 'store' for h in hits),
                'hits': hits
            })
    return output

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory', help='inspect_disc.py --json')
    p.add_argument('--target', type=lambda s: int(s, 0), default=DEFAULT_TARGET)
    p.add_argument('--max-bytes-per-bin', type=lambda s: int(s, 0), default=1024*1024)
    args = p.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    report = audit(args.image, entries, args.target, args.max_bytes_per_bin)
    cdef = next((e for e in report if e['path'] == '/BIN/CDEF.BIN;1'), None)
    mirror = None
    if cdef and cdef['complete_file_examined']:
        record = next(e for e in entries if e['path'] == '/BIN/CDEF.BIN;1')
        with open(args.image,'rb') as disc:
            blob = read_prefix(disc,record,record['size'])
        mirror = {
            'offset_a': '0x38000', 'offset_b': '0x3c000',
            'identical_prefix_bytes': common_prefix(blob[0x38000:0x3c000],
                                                    blob[0x3c000:0x40000])}
    print(json.dumps({'target': f'0x{args.target:08x}',
                      'results': report, 'cdef_region_comparison': mirror},indent=2))

if __name__ == '__main__':
    main()
