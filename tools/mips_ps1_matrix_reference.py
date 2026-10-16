"""Private, fail-closed numerical reference comparison for PS-X MIPS matrices.

The input JSON is a *claim* of a capture: its source cannot be authenticated
by this program. A successful comparison proves agreement with the supplied
nine halfwords, NOT correspondence with original PlayStation hardware.

Do not log the JSON, original image, guest PCs, registers, RAM or coefficients.
"""
import hashlib
import re
import struct

try:
    from .audit_original_nclip_winding import parse_exe
    from .mips_control_flow import execute, STORES
    from .mips_matrix_memory import MappedMemory, matrix_coefficients
except ImportError:
    from audit_original_nclip_winding import parse_exe
    from mips_control_flow import execute, STORES
    from mips_matrix_memory import MappedMemory, matrix_coefficients

SCHEMA = 'wild-arms-ps1-matrix-reference-v1'
_MAX_PATCHES = 256
_MAX_PATCH_BYTES = 4 * 1024 * 1024
_SAFE_REASONS = frozenset(('stop_pc', 'end_of_image', 'step_limit',
                           'pc_outside_image', 'ValueError', 'OverflowError'))


def _u32(value):
    if type(value) is int and 0 <= value <= 0xffffffff:
        return value
    if isinstance(value, str) and re.fullmatch(r'0[xX][0-9a-fA-F]{1,8}', value):
        return int(value, 16)
    raise ValueError('invalid unsigned 32-bit fixture field')


def _decode_reference(fixture, exe_sha):
    if not isinstance(fixture, dict) or fixture.get('schema') != SCHEMA:
        raise ValueError('unsupported reference fixture schema')
    if fixture.get('source') not in ('synthetic', 'external_ps1_capture_claim'):
        raise ValueError('unrecognized fixture source claim')
    sha = fixture.get('exe_sha256')
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
        raise ValueError('invalid executable checksum field')
    if sha != exe_sha:
        raise ValueError('executable SHA-256 does not match fixture')
    regs = fixture.get('gpr')
    if not isinstance(regs, list) or len(regs) != 32:
        raise ValueError('reference must include all 32 general registers')
    regs = [_u32(x) for x in regs]
    if regs[0] != 0:
        raise ValueError('zero register must be zero')
    expected = fixture.get('expected_matrix_s16')
    if (not isinstance(expected, list) or len(expected) != 9 or
            any(type(v) is not int or not -32768 <= v <= 32767 for v in expected)):
        raise ValueError('expected exactly nine signed 16-bit coefficients')
    start, stop, matrix = (_u32(fixture[name]) for name in
                           ('entry_pc', 'stop_pc', 'matrix_address'))
    if start & 3 or stop & 3 or matrix & 1 or matrix > 0xffffffff - 17:
        raise ValueError('unaligned reference entry/stop/matrix pointer')
    hi, lo = _u32(fixture['hi']), _u32(fixture['lo'])
    max_steps = fixture.get('max_steps', 4096)
    if type(max_steps) is not int or not 1 <= max_steps <= 100000:
        raise ValueError('invalid bounded instruction budget')
    segments = fixture.get('memory_segments')
    if not isinstance(segments, list) or len(segments) > _MAX_PATCHES:
        raise ValueError('invalid reference memory segments')
    parsed = []
    total = 0
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError('malformed reference memory segment')
        addr = _u32(segment.get('address'))
        content = segment.get('data_hex')
        if (not isinstance(content, str) or len(content) < 2 or len(content) & 1 or
                len(content) > 2 * _MAX_PATCH_BYTES or
                not re.fullmatch('[0-9a-fA-F]+', content)):
            raise ValueError('invalid memory segment hex')
        data = bytes.fromhex(content)
        total += len(data)
        if total > _MAX_PATCH_BYTES or addr + len(data) > 0x100000000:
            raise ValueError('reference snapshot memory budget exceeded')
        parsed.append((addr, data))
    return {'source':fixture['source'], 'gpr':regs, 'expected':expected,
            'entry_pc':start,'stop_pc':stop, 'matrix_address':matrix,
            'hi':hi,'lo':lo,'max_steps':max_steps,'segments':parsed}


def _prepare_memory(image, base, segments):
    """Apply captured RAM bytes over EXE image or map disjoint regions.

    Overlaps among explicit segments are rejected; no missing RAM is filled in.
    A segment straddling the EXE image is split into adjacent mapped ranges.
    """
    image = bytearray(image)
    end = base + len(image)
    sorted_segments = sorted(segments, key=lambda x:x[0])
    for (address, data), (next_address, _) in zip(sorted_segments,sorted_segments[1:]):
        if address + len(data) > next_address:
            raise ValueError('overlapping snapshot segments')
    extras = []
    overwritten_image = False
    for address, data in sorted_segments:
        seg_end = address + len(data)
        # A captured PS1 RAM segment may straddle the executable image.
        # Preserve bytes on both sides and overlay its middle image section
        # without producing overlapping mapped regions.
        if address < base:
            below_end = min(seg_end, base)
            if below_end > address:
                extras.append((address, data[:below_end-address]))
        inner_start, inner_end = max(address, base), min(seg_end, end)
        if inner_start < inner_end:
            image[inner_start-base:inner_end-base] = data[inner_start-address:inner_end-address]
            overwritten_image = True
        if seg_end > end:
            above_start = max(address, end)
            if seg_end > above_start:
                extras.append((above_start, data[above_start-address:]))
        # Segments entirely outside the executable interval are mapped once.
        if seg_end <= base or address >= end:
            # Recovered below/above part is already in extras.
            pass
    memory = MappedMemory().map_region(base, image, writable=True)
    for address, data in extras:
        memory.map_region(address, data, writable=True)
    return memory, bytes(image), overwritten_image


def _final_sh_slots(code, base, trace, matrix_address):
    """Validate last complete SH write for each halfword, including overlaps."""
    slots = [False]*9
    stores = iter(trace['store_addresses'])
    for pc in trace['visited_pcs']:
        if pc < base or pc + 4 > base + len(code) or (pc-base) & 3:
            raise ValueError('executed instruction outside PS-X EXE image')
        word, = struct.unpack_from('<I',code,pc-base)
        op = word >> 26
        if op not in STORES:
            continue
        addr = next(stores, None)
        width = STORES[op]
        if type(addr) is not int or addr < 0 or addr % width:
            raise ValueError('inconsistent executed MIPS store trace')
        for i in range(9):
            start = matrix_address + i*2
            if addr < start+2 and addr+width > start:
                slots[i] = bool(op == 41 and addr == start)
    if next(stores, None) is not None:
        raise ValueError('unconsumed MIPS store events')
    return slots


def compare(blob, fixture):
    """Compare against user-provided numerical expectations without leaking them.

    Comparison only runs if the bounded execution *completed at stop_pc*
    and each final matrix halfword was last written by SH.  The source
    of the provided expected coefficients is NOT independently verified.
    """
    if not isinstance(blob, bytes):
        raise ValueError('PS-X EXE must be supplied as bytes')
    sha = hashlib.sha256(blob).hexdigest()
    capture = _decode_reference(fixture, sha)
    base, image = parse_exe(blob)
    if not base <= capture['entry_pc'] < base+len(image):
        raise ValueError('fixture entry outside PS-X EXE image')
    memory, code, overlaid = _prepare_memory(image, base, capture['segments'])
    try:
        for i in range(9):
            memory.read(capture['matrix_address'] + 2*i, 2)
    except ValueError:
        raise ValueError('snapshot must map all nine matrix halfwords') from None
    trace = execute(code, base, capture['entry_pc'], memory, capture['gpr'],
                    hi=capture['hi'], lo=capture['lo'],
                    stop_pc=capture['stop_pc'],max_steps=capture['max_steps'])
    final_sh = _final_sh_slots(code,base,trace,capture['matrix_address'])
    at_stop = trace['completed'] and trace['reason'] == 'stop_pc'
    eligible = bool(at_stop and all(final_sh))
    mismatch_indices = []
    match_count = 0
    if eligible:
        actual = matrix_coefficients(memory,capture['matrix_address'])
        mismatch_indices = [i for i,(a,b) in enumerate(zip(actual,capture['expected']))
                            if a != b]
        match_count = 9 - len(mismatch_indices)
    return {
        'reference_schema': SCHEMA,
        'sha256_match': True,
        'executable_memory_overlaid': overlaid,
        'guest_completed_at_expected_stop': bool(at_stop),
        'guest_stop_reason': trace['reason'] if trace['reason'] in _SAFE_REASONS else 'other',
        'final_halfword_slots_written_by_sh':sum(final_sh),
        'all_nine_final_sh_verified':all(final_sh),
        'coefficient_comparison_performed':eligible,
        'matching_coefficient_count':match_count if eligible else None,
        'mismatch_slot_indices':mismatch_indices if eligible else [],
        'matches_supplied_nine_coefficients':bool(eligible and not mismatch_indices),
        'supplied_reference_is_claimed_external_capture': (
            capture['source'] == 'external_ps1_capture_claim'),
        'external_ps1_capture_authenticity_independently_verified':False,
        'original_playstation_hardware_equivalence_proven':False,
        'guest_code_mutation_modeled':False,
        'native_switch_port_proven':False,
        'private_values_emitted':False,
    }
