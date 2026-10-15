#!/usr/bin/env python3
"""Classify OT packet triangle layouts using observed SXY write offsets, not GP0 opcode."""
import argparse
import json
from pathlib import Path
try:
    from .audit_nclip_ot_packets import audit
    from .audit_original_nclip_winding import parse_exe
except ImportError:
    from audit_nclip_ot_packets import audit
    from audit_original_nclip_winding import parse_exe

# Offset is relative to GPU packet tag word, not the first GPU command word.
TRIANGLES = {
    4: ('F3', (8, 12, 16), (0x20, 0x21, 0x22, 0x23)),
    6: ('G3', (8, 16, 24), (0x30, 0x31, 0x32, 0x33)),
    7: ('FT3', (8, 16, 24), (0x24, 0x25, 0x26, 0x27)),
    9: ('GT3', (8, 20, 32), (0x34, 0x35, 0x36, 0x37)),
}

def identify_layout(packet_words, stores, packet_base_register):
    result = {'layout_candidate': None, 'expected_gp0_opcode_range': None,
              'observed_gp0_opcode': None, 'opcode_verified': False}
    entry = TRIANGLES.get(packet_words)
    if entry is None:
        return result
    family, offsets, opcodes = entry
    coords = [x for x in stores if x['register'] in ('SXY0', 'SXY1', 'SXY2')
              and x['base_register'] == packet_base_register]
    if len(coords) != 3:
        return result
    by_name = {x['register']: x['offset'] for x in coords}
    if len(by_name) != 3 or tuple(by_name.get(f'SXY{i}') for i in range(3)) != offsets:
        return result
    result['layout_candidate'] = family
    result['expected_gp0_opcode_range'] = [f'0x{x:02X}' for x in opcodes]
    return result

def inspect_layouts(image, base):
    report = audit(image, base)
    counts = {}
    for site in report['sites']:
        packet = site.get('ot_packet')
        site['gp0_layout'] = identify_layout(
            packet['packet_words'], site['sxy_stores'],
            packet['packet_base_register']) if packet else None
        layout = site['gp0_layout']
        if layout and layout['layout_candidate']:
            key = layout['layout_candidate']
            counts[key] = counts.get(key, 0) + 1
    return {'nclip_count': report['nclip_count'],
            'ot_packet_candidates': report['ot_packet_candidates'],
            'layout_matched': sum(counts.values()),
            'counts_by_layout': counts, 'sites': report['sites']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path, help='private locally extracted PS-X EXE')
    args = parser.parse_args()
    base, image = parse_exe(args.exe.read_bytes())
    print(json.dumps(inspect_layouts(image, base), indent=2))

if __name__ == '__main__':
    main()
