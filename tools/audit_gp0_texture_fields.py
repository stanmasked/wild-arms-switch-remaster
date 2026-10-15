#!/usr/bin/env python3
"""Inspect direct writes to textured-triangle UV/CLUT/TPAGE words in NCLIP paths.

This is static same-base-register evidence, not whole-program dataflow.
"""
import argparse
import json
import struct
from pathlib import Path
try:
    from .audit_gp0_triangle_layouts import inspect_layouts
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_gp0_triangle_layouts import inspect_layouts
    from audit_original_nclip_winding import parse_exe

TEXTURE_FIELDS = {'FT3': (12, 20, 28), 'GT3': (12, 24, 36)}
STORE_WIDTH = {0x28: 1, 0x29: 2, 0x2b: 4, 0x3a: 4}


def decode_store(word):
    op = word >> 26
    if op not in STORE_WIDTH:
        return None
    offset = word & 0xffff
    if offset >= 0x8000:
        offset -= 0x10000
    return {'base': (word >> 21) & 31, 'source': (word >> 16) & 31,
            'offset': offset, 'size': STORE_WIDTH[op],
            'instruction': {0x28: 'SB', 0x29: 'SH', 0x2b: 'SW', 0x3a: 'SWC2'}[op]}


def scan_field_writes(image, base, start, stop, packet_register, fields):
    """Only the linear interval [start,stop). Delay slots excluded by caller."""
    if (start < base or stop > base + len(image) or start > stop or
            (start-base) % 4 or (stop-base) % 4):
        return []
    events = []
    for address in range(start, stop, 4):
        word = struct.unpack_from('<I', image, address-base)[0]
        store = decode_store(word)
        if not store or store['base'] != packet_register:
            continue
        overlaps = [f'UV{i}_CLUT_TPAGE' for i, field in enumerate(fields)
                    if store['offset'] < field + 4 and
                    store['offset'] + store['size'] > field]
        if overlaps:
            events.append({'address': f'0x{address:08X}',
                           'instruction': store['instruction'],
                           'offset': store['offset'], 'size': store['size'],
                           'overlaps': overlaps})
    return events


def audit_texture_fields(image, base):
    report = inspect_layouts(image, base)
    textured = 0
    with_writes = 0
    for site in report['sites']:
        site['texture_fields'] = None
        family = (site.get('gp0_layout') or {}).get('layout_candidate')
        packet = site.get('ot_packet')
        if family not in TEXTURE_FIELDS or not packet or not site['blez']:
            continue
        textured += 1
        fields = TEXTURE_FIELDS[family]
        branch = int(site['blez'], 16)
        end = int(site['branch_target'], 16)
        writes = scan_field_writes(image, base, branch+8, end,
                                   packet['packet_base_register'], fields)
        with_writes += bool(writes)
        site['texture_fields'] = {
            'family_candidate': family,
            'expected_word_offsets': list(fields),
            'fallthrough_direct_writes': writes,
            'direct_write_found': bool(writes),
            'initialization_traced': False,
        }
    return {'textured_packet_candidates': textured,
            'textured_paths_with_direct_field_writes': with_writes,
            'initial_uv_values_recovered': 0,
            'sites': report['sites']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe', type=Path, help='locally extracted original PS-X EXE')
    args = p.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(audit_texture_fields(image, base), indent=2))


if __name__ == '__main__':
    main()
