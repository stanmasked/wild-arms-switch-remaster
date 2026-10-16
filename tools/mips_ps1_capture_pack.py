"""Build a private PS1 matrix reference from two raw RAM dumps and debugger PCs.

Input capture authenticity is not independently verifiable. The files must
represent the SAME play session at the precise pre-builder and post-return
instruction boundaries. No registers, RAM or coefficient values are printed.
"""
import hashlib
import struct

from .audit_original_nclip_winding import parse_exe
from .mips_ps1_matrix_reference import SCHEMA, _decode_reference, _u32
from .mips_final_cpu_state import decode_expected
from .mips_final_memory_state import pack as pack_final_ram
from .mips_store_event_sequence import decode as decode_store_events

RAM_LIMIT = 4 * 1024 * 1024
REGISTERS_SCHEMA = 'wild-arms-ps1-debugger-registers-v1'


def _parse_register_snapshot(raw, *, require_gpr):
    if not isinstance(raw, dict) or raw.get('schema') != REGISTERS_SCHEMA:
        raise ValueError('invalid debugger register snapshot schema')
    pc = _u32(raw.get('pc'))
    if pc & 3:
        raise ValueError('unaligned debugger stop PC')
    if not require_gpr:
        # Missing optional post-state is allowed unless strict comparison is
        # explicitly requested; never infer final GPRs from the initial ones.
        has_any_final = any(key in raw for key in
            ('gpr','hi','lo','pending_load','in_branch_delay_slot'))
        if not has_any_final:
            return {'pc': pc, 'final_cpu': None}
        final = decode_expected({key: raw[key] for key in
           ('gpr','hi','lo','pending_load','in_branch_delay_slot') if key in raw})
        return {'pc': pc, 'final_cpu': {key: raw[key] for key in
            ('gpr','hi','lo','pending_load','in_branch_delay_slot')}}
    gprs = raw.get('gpr')
    if not isinstance(gprs, list) or len(gprs) != 32:
        raise ValueError('pre-call snapshot requires all 32 GPR values')
    values = [_u32(v) for v in gprs]
    if values[0] != 0:
        raise ValueError('r0 must equal zero')
    if 'pending_load' not in raw or 'in_branch_delay_slot' not in raw:
        raise ValueError('debugger capture must declare MIPS pipeline state')
    # Pipeline interpretation and word-range checks belong to stage 211's
    # strict fixture decoder, avoiding two conflicting implementations.
    return {'pc': pc, 'gpr': values,
            'hi': _u32(raw.get('hi')), 'lo': _u32(raw.get('lo')),
            'pending_load': raw['pending_load'],
            'in_branch_delay_slot': raw['in_branch_delay_slot']}


def pack(exe_blob, before_registers, after_registers, before_ram, after_ram,
         *, ram_base=0x80000000, matrix_address=None,
         source='external_ps1_capture_claim', max_steps=4096,
         require_completed_jr_ra=False, require_final_cpu_state=False,
         require_final_memory_state=False, store_sequence=None,
         require_store_sequence=False):
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
    if type(require_store_sequence) is not bool:
        raise ValueError('invalid store sequence requirement')
    if require_store_sequence and store_sequence is None:
        raise ValueError('missing debugger store-event sequence')
    if store_sequence is not None:
        decode_store_events(store_sequence)
    if type(require_final_memory_state) is not bool:
        raise ValueError('invalid full final RAM requirement')
    if type(require_final_cpu_state) is not bool:
        raise ValueError('invalid strict final CPU requirement')
    if require_final_cpu_state and after['final_cpu'] is None:
        raise ValueError('complete debugger after-registers state required')
    if type(require_completed_jr_ra) is not bool:
        raise ValueError('invalid strict return boundary request')
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
        'pending_load': before['pending_load'],
        'in_branch_delay_slot': before['in_branch_delay_slot'],
        'max_steps': max_steps,
        'require_completed_jr_ra': require_completed_jr_ra,
        'require_final_cpu_state': require_final_cpu_state,
        'require_final_memory_state': require_final_memory_state,
        'require_store_sequence': require_store_sequence,
        'memory_segments': [{'address': base, 'data_hex': before_ram.hex()}],
        'expected_matrix_s16': expected,
    }
    if store_sequence is not None:
        fixture['expected_store_sequence'] = store_sequence
    if require_final_memory_state:
        fixture['expected_final_memory_state'] = pack_final_ram(
            before_ram, after_ram, base, matrix)
    if after['final_cpu'] is not None:
        fixture['expected_final_cpu_state'] = after['final_cpu']
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
