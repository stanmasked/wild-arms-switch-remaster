"""Sanitized counts for *successful* concrete MIPS memory reads.

The raw (PC, address, width, destination GPR) tuples are internal to the
interpreter; this classifier exports NO address, data, table index or value.
It makes no claim that a table read reveals the game's input rotation angles.
"""
from collections import Counter

try:
    from .audit_gp0_trig_table import TABLE, ENTRIES, TABLE_LOAD_PCS
except ImportError:
    from audit_gp0_trig_table import TABLE, ENTRIES, TABLE_LOAD_PCS


def summarize(loads, *, image_base, image_size, stack_base, stack_size,
              matrix_address, matrix_size=18, table_address=TABLE,
              table_entries=ENTRIES, known_lookup_pcs=TABLE_LOAD_PCS):
    """Classify executed loads by mapped region, without guest values/addresses.

    Trig-table accesses count as packed entries only for a complete aligned LW.
    An LW at a known lookup PC is *not* proof of table access unless the
    resolved runtime address falls inside the table region.
    """
    if any(not isinstance(v, int) or v < 0 for v in (
            image_base, image_size, stack_base, stack_size,
            matrix_address, matrix_size, table_address, table_entries)):
        raise ValueError('invalid memory boundaries')
    ranges = {
        'matrix_buffer': (matrix_address, matrix_address + matrix_size),
        'trig_table': (table_address, table_address + table_entries * 4),
        'scratch_stack': (stack_base, stack_base + stack_size),
        'loaded_exe': (image_base, image_base + image_size),
    }
    groups = Counter()
    packed_entries = set()
    touched_known_sites = set()
    all_known_sites = set(known_lookup_pcs)
    destinations = set()
    for event in loads:
        if len(event) != 4:
            raise ValueError('invalid read event')
        pc, address, width, dst = event
        if (not all(isinstance(v, int) for v in event)
                or width not in (1, 2, 4) or address < 0
                or address % width or pc % 4 or not 0 <= dst <= 31):
            raise ValueError('invalid memory read event')
        destinations.add(dst)
        start, end = ranges['trig_table']
        if start <= address and address + width <= end:
            if width == 4 and (address - start) % 4 == 0:
                groups['packed_trig_lw'] += 1
                packed_entries.add((address - start) // 4)
                if pc in all_known_sites:
                    touched_known_sites.add(pc)
            else:
                groups['partial_trig_read'] += 1
        elif (ranges['matrix_buffer'][0] <= address
              and address + width <= ranges['matrix_buffer'][1]):
            groups['matrix_buffer_read'] += 1
        elif (ranges['scratch_stack'][0] <= address
              and address + width <= ranges['scratch_stack'][1]):
            groups['scratch_stack_read'] += 1
        elif (ranges['loaded_exe'][0] <= address
              and address + width <= ranges['loaded_exe'][1]):
            groups['other_loaded_exe_read'] += 1
        else:
            groups['other_mapped_read'] += 1
    names = ('packed_trig_lw', 'partial_trig_read', 'matrix_buffer_read',
             'scratch_stack_read', 'other_loaded_exe_read', 'other_mapped_read')
    return {
        'successful_load_count': len(loads),
        'read_groups': {name: groups[name] for name in names},
        'distinct_packed_trig_entries': len(packed_entries),
        'known_lookup_sites_with_packed_reads': len(touched_known_sites),
        'known_lookup_site_count': len(all_known_sites),
        'destination_gprs': sorted(destinations),
        'original_rotation_angles_recovered': False,
        'private_values_emitted': False,
    }
