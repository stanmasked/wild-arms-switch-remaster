"""Restricted static PS1 record-index pointer-use evidence.

No original game bytes, guest instruction addresses, field offsets or
private RAM are emitted. A matching opcode shape is not runtime proof.
"""
import argparse
import json
from pathlib import Path

try:
    from .verify_record_stride import (
        TARGETS, INDEX_WORDS, GLOBAL_WORDS, _static_index_scale,
        read_raw_iso_entry,
    )
except ImportError:
    from verify_record_stride import (
        TARGETS, INDEX_WORDS, GLOBAL_WORDS, _static_index_scale,
        read_raw_iso_entry,
    )

SCHEMA = 'wild-arms-ps1-record-pointer-use-evidence-v1'
MAX_EXE_BYTES = 4 * 1024 * 1024
WINDOW_WORDS = 21
# MIPS ADDU v1,v1,v0 or ADDU v1,v0,v1; both retain the index term.
_POINTER_ADDS = frozenset((0x00621821, 0x00431821))
# MIPS loads and stores. We classify only a direct v1-based memory access.
_MEMORY_OPS = frozenset((32, 33, 35, 36, 37, 40, 41, 43))


def _classify_tail(words):
    """Conservative straight-line syntactic pattern, not actual execution.

    Ignore only literal NOPs. Unexpected opcodes, even harmless ones, leave
    the classification unresolved instead of guessing about register state.
    """
    added = False
    for word in words:
        if word == 0:
            continue
        if word in _POINTER_ADDS and not added:
            added = True
            continue
        if (word >> 26) in _MEMORY_OPS and ((word >> 21) & 31) == 3:
            return 'direct_add_and_access' if added else 'unresolved'
        return 'unresolved'
    return 'add_without_access' if added else 'unresolved'


def inspect(exe_data):
    """Audit all three predeclared sites without asserting struct layout.

    For every site, require the exact index prefix and bounded 21-word
    window before summarizing any count. A single mismatch aborts the
    entire report, so no per-site evidence leaks from partial inspection.
    """
    if (not isinstance(exe_data, (bytes, bytearray))
            or len(exe_data) < 2048 or exe_data[:8] != b'PS-X EXE'):
        raise ValueError('invalid PS-X EXE')
    base = int.from_bytes(exe_data[0x18:0x1c], 'little')
    size = int.from_bytes(exe_data[0x1c:0x20], 'little')
    if not 0 < size <= MAX_EXE_BYTES or len(exe_data) < 2048 + size:
        raise ValueError('invalid bounded EXE image')
    counts = {'direct_add_and_access': 0, 'add_without_access': 0,
              'unresolved': 0}
    for target in TARGETS:
        offset = 2048 + target - base
        if offset < 2048 or offset + WINDOW_WORDS * 4 > 2048 + size:
            raise ValueError('record index window outside EXE')
        words = [int.from_bytes(exe_data[offset+i:offset+i+4], 'little')
                 for i in range(0, WINDOW_WORDS * 4, 4)]
        # This validates all eleven words, including the original LW.
        scale = _static_index_scale(words[:8], words[8:11])
        if scale != 2708:
            raise ValueError('unverified record index scale')
        counts[_classify_tail(words[11:])] += 1
    return {
        'schema': SCHEMA,
        'matched_prefix_sites': len(TARGETS),
        'static_index_coefficient': 2708,
        'direct_add_and_memory_access_patterns': counts['direct_add_and_access'],
        'add_without_memory_access_patterns': counts['add_without_access'],
        'unresolved_post_index_patterns': counts['unresolved'],
        'syntactic_evidence_only': True,
        'executed_pointer_use_verified': False,
        'record_size_verified': False,
        'playstation_hardware_equivalence_verified': False,
        'private_game_data_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path,
                        help='Private inspect_disc.py --json inventory')
    args = parser.parse_args(argv)
    entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
    matches = [row for row in entries
               if row.get('path') == '/EXE/WILDARMS.EXE;1'
               and not row.get('directory', False)]
    if len(matches) != 1:
        parser.error('expected one main EXE entry')
    report = inspect(read_raw_iso_entry(args.disc, matches[0]))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
