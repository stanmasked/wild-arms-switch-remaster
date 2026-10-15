#!/usr/bin/env python3
"""Find GTE RGB0..RGB2 FIFO stores in original Wild Arms GPU polygon packets."""
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

COLOR_OFFSETS = {'G3': (4, 12, 20), 'GT3': (4, 16, 28)}

def decode_swc2(word):
    if word >> 26 != 0x3a:
        return None
    offset = word & 0xffff
    if offset >= 32768:
        offset -= 65536
    return {'base': (word >> 21) & 31,
            'gte_register': (word >> 16) & 31, 'offset': offset}

def scan_rgb_writes(image, base, branch, target, packet_reg):
    """Exclude the BLEZ delay slot from fallthrough RGB write evidence."""
    start = branch + 8
    if start < base or target > base + len(image) or target <= start:
        return []
    result = []
    for address in range(start, target, 4):
        word = struct.unpack_from('<I', image, address-base)[0]
        store = decode_swc2(word)
        if store is None or store['base'] != packet_reg:
            continue
        if store['gte_register'] not in (20, 21, 22):
            continue
        result.append({'address': f'0x{address:08X}',
                       'register': f'RGB{store["gte_register"]-20}',
                       'offset': store['offset']})
    return result

def audit_colors(image, base):
    report = inspect_layouts(image, base)
    counts = {'matching_rgb_fifo_triplets': 0, 'gt3_matching': 0,
              'g3_matching': 0}
    for site in report['sites']:
        site['rgb_fifo_stores'] = []
        site['rgb_fifo_matches_layout'] = False
        packet = site.get('ot_packet')
        layout = (site.get('gp0_layout') or {}).get('layout_candidate')
        if not packet or not site['blez']:
            continue
        branch = int(site['blez'], 16)
        target = int(site['branch_target'], 16)
        stores = scan_rgb_writes(image, base, branch, target,
                                 packet['packet_base_register'])
        site['rgb_fifo_stores'] = stores
        expected = COLOR_OFFSETS.get(layout)
        by_register = {x['register']: x['offset'] for x in stores}
        match = (expected is not None and len(stores) == 3 and
                 tuple(by_register.get(f'RGB{i}') for i in range(3)) == expected)
        site['rgb_fifo_matches_layout'] = match
        if match:
            counts['matching_rgb_fifo_triplets'] += 1
            counts[f'{layout.lower()}_matching'] += 1
    return {'layout_counts': report['counts_by_layout'], 'counts': counts,
            'gp0_opcode_bytes_verified': 0, 'sites': report['sites']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(audit_colors(image, base), indent=2))

if __name__ == '__main__':
    main()
