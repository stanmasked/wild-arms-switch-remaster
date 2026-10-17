#!/usr/bin/env python3
"""Verify record stride and field offsets in user-owned PS-X EXE, read-only."""
import argparse
import json
from pathlib import Path

TARGETS = (0x8006d258, 0x8006dca0, 0x8006dcec)
INDEX_WORDS = (
    0x00051080, 0x00451021, 0x00021080, 0x00451021,
    0x000210c0, 0x00451021, 0x00021080, 0x00451021,
)
GLOBAL_WORDS = (0x3c03800d, 0x8c632c3c, 0x00021080)
# Existing 364-byte field assumption is NOT validated by INDEX_WORDS.
# Word 0x000210c0 shifts by three bits, and these words imply 2708 bytes.
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

def stride_from_index_words(words):
    if tuple(words) != INDEX_WORDS:
        raise ValueError('index sequence differs from known MIPS pattern')
    a, v = 1, 0
    for word in words:
        funct = word & 63
        if funct == 0:  # sll v0,v0|a1,shift
            source = (word >> 16) & 31
            shift = (word >> 6) & 31
            v = (a if source == 5 else v) << shift
        elif funct == 0x21:  # addu v0,v0,a1
            v += a
        else:
            raise ValueError('unsupported instruction')
    return v * 4  # trailing sll v0,v0,2

def inspect_exe(exe_data):
    if exe_data[:8] != b'PS-X EXE' or len(exe_data) < 2048:
        raise ValueError('invalid PS-X EXE')
    base = int.from_bytes(exe_data[0x18:0x1c], 'little')
    size = int.from_bytes(exe_data[0x1c:0x20], 'little')
    if size <= 0 or len(exe_data) < 2048 + size:
        raise ValueError('truncated EXE')
    results = []
    for target in TARGETS:
        pos = 2048 + target - base
        if pos < 2048 or pos + 0x54 > 2048 + size:
            raise ValueError('target outside EXE range')
        words = [int.from_bytes(exe_data[pos+i:pos+i+4], 'little')
                 for i in range(0, 0x54, 4)]
        if tuple(words[:8]) != INDEX_WORDS or tuple(words[8:11]) != GLOBAL_WORDS:
            raise ValueError('unexpected index prefix')
        # The existing 364-byte stride claim conflicts with the exact
        # INDEX_WORDS arithmetic (currently 2708 bytes including its final
        # SLL). Do not publish a hard-coded 364 as a verified observation.
        # Require a revalidated instruction trace before trusting this field.
        if stride_from_index_words(words[:8]) != 364:
            raise ValueError('unverified record stride: MIPS arithmetic contradicts 364')
        # After eleven prefix instructions each function computes v1 = base + v0.
        # CDGD function at 0x8006dca0 branches before that addition.
        fields = sorted({(w & 0xffff) for w in words[11:]
                         if ((w >> 26) in (32, 33, 35, 36, 37, 40, 41, 43)) and
                         ((w >> 21) & 31) == 3})
        results.append({'target': f'0x{target:08x}', 'stride_bytes': 364,
                        'global_pointer_location': '0x800d2c3c',
                        'field_offsets_observed_in_0x54_bytes': [f'0x{x:x}' for x in fields]})
    return results

def read_raw_iso_entry(image, entry):
    if entry['size'] > 4 * 1024 * 1024:
        raise ValueError('refuse oversized executable')
    data = bytearray()
    with open(image, 'rb') as f:
        for n in range((entry['size'] + 2047) // 2048):
            f.seek((entry['lba'] + n) * 2352)
            sector = f.read(2352)
            if len(sector) != 2352 or sector[:12] != SYNC or sector[15] != 2:
                raise ValueError('invalid MODE2 sector')
            if sector[18] & 0x20 or sector[16:20] != sector[20:24]:
                raise ValueError('expected XA Form1')
            data.extend(sector[24:2072])
    return bytes(data[:entry['size']])

def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('inventory', help='inspect_disc.py --json')
    args = p.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    matches = [x for x in entries if x['path'] == '/EXE/WILDARMS.EXE;1']
    if len(matches) != 1:
        p.error('WILDARMS.EXE not found')
    print(json.dumps(inspect_exe(read_raw_iso_entry(args.image, matches[0])), indent=2))

if __name__ == '__main__':
    main()
