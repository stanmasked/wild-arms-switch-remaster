"""Build a private PS1 matrix reference from two raw RAM dumps and debugger PCs.

Input capture authenticity is not independently verifiable. The files must
represent the SAME play session at the precise pre-builder and post-return
instruction boundaries. No registers, RAM or coefficient values are printed.
"""
import hashlib
import struct

from .audit_original_nclip_winding import parse_exe
from .mips_ps1_matrix_reference import SCHEMA, _decode_reference, _u32

RAM_LIMIT = 4 * 1024 * 1024
REGISTERS_SCHEMA = 'wild-arms-ps1-debugger-registers-v1'


def _parse_register_snapshot(raw, *, require_gpr):
    if not isinstance(raw, dict) or raw.get('schema') != REGISTERS_SCHEMA:
        raise ValueError('invalid debugger register snapshot schema')
    pc = _u32(raw.get('pc'))
    if pc & 3:
        raise ValueError('unaligned debugger stop PC')
    if not require_gpr:
        # Do not infer the after-PC from the old RA register or a guess.
        return {'pc': pc}
    gprs = raw.get('gpr')
    if not isinstance(gprs, list) or len(gprs) != 32:
        raise ValueError('pre-call snapshot requires all 32 GPR values')
    values = [_u32(v) for v in gprs]
    if values[0] != 0:
        raise ValueError('r0 must equal zero')
    return {'pc': pc, 'gpr': values,
            'hi': _u32(raw.get('hi')), 'lo': _u32(raw.get('lo'))}


def pack(exe_blob, before_registers, after_registers, before_ram, after_ram,
         *, ram_base=0x80000000, matrix_address=None,
         source='external_ps1_capture_claim', max_steps=4096):
    """Return a stage-211 reference fixture, never log or print it.

    `before_ram` is the guest's memory AT the before_registers PC (before
    executing that instruction); after_ram is captured AT the after PC (after
    the final matrix SH and return delay slot).  Address bases are *guest
    virtual* addresses, not the raw offset in the dumped physical RAM file.
    """
    if not isinstance(exe_blob, bytes):
        raise ValueError('EXE must be bytes')
    if not isinstance(before_ram, bytes) or not isinstance(after_ram, bytes):
        raise ValueError('binary RAM captures are required')
    if (not 18 <= len(before_ram) <= RAM_LIMIT or
            len(after_ram) != len(before_ram)):
        raise ValueError('RAM dumps must have equal sizes between 18 bytes and 4 MiB')
    base = _u32(ram_base)
    if base + len(before_ram) > 0x100000000:
        raise ValueError('RAM mapping exceeds 32-bit guest address space')
    before = _parse_register_snapshot(before_registers, require_gpr=True)
    after = _parse_register_snapshot(after_registers, require_gpr=False)
    if before['pc'] == after['pc']:
        raise ValueError('before and after debugger PCs must differ')
    exe_base, image = parse_exe(exe_blob)
    if not exe_base <= before['pc'] < exe_base+len(image):
        raise ValueError('before debugger PC is outside loaded executable')
    if matrix_address is None:
        matrix = before['gpr'][5]  # a1 as in the known builder calling contract
    else:
        matrix = _u32(matrix_address)
    if matrix & 1 or matrix < base or matrix + 18 > base + len(after_ram):
        raise ValueError('all matrix halfwords must fit the RAM capture')
    if source not in ('synthetic', 'external_ps1_capture_claim'):
        raise ValueError('unrecognized provenance claim')
    if type(max_steps) is not int or not 1 <= max_steps <= 100000:
        raise ValueError('invalid MIPS instruction budget')
    offset = matrix - base
    expected = list(struct.unpack_from('<9h', after_ram, offset))
    sha = hashlib.sha256(exe_blob).hexdigest()
    fixture = {
        'schema': SCHEMA,
        'source': source,
        'exe_sha256': sha,
        'entry_pc': before['pc'],
        'stop_pc': after['pc'],
        'matrix_address': matrix,
        'gpr': before['gpr'],
        'hi': before['hi'],
        'lo': before['lo'],
        'max_steps': max_steps,
        'memory_segments': [{'address': base, 'data_hex': before_ram.hex()}],
        'expected_matrix_s16': expected,
    }
    # Reuse stage-211 validation before ever persisting a private artifact.
    _decode_reference(fixture, sha)
    return fixture


def summarize_capture(fixture):
    """Public-safe counters only, with no file paths, PCs or guest values."""
    return {
        'capture_package_prepared': True,
        'reference_schema': SCHEMA,
        'register_count': len(fixture['gpr']),
        'before_ram_segment_count': len(fixture['memory_segments']),
        'after_matrix_coefficient_count': len(fixture['expected_matrix_s16']),
        'ps1_capture_authenticity_independently_verified': False,
        'same_game_session_verified': False,
        'numerical_comparison_performed': False,
        'private_values_emitted': False,
    }
