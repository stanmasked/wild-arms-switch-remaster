"""Private after-RAM block-hash oracle for bounded PS1 MIPS replay.

Only block *indices*, changed-byte counts and booleans leave the module;
never output RAM bytes, SHA-256 block digests, virtual addresses or values.
Authenticity of purported PS1 debugger snapshots is not established here.
"""
import hashlib
import re

BLOCK_SIZE = 4096
MAX_BYTES = 4 * 1024 * 1024


def changed_outside_matrix(before, after, address, matrix_address):
    """Count changed bytes excluding the known 18-byte matrix (no allocation)."""
    if len(before) != len(after):
        raise ValueError('RAM snapshot lengths differ')
    lo, hi = matrix_address - address, matrix_address - address + 18
    return sum(a != b for i, (a, b) in enumerate(zip(before, after))
               if not lo <= i < hi)


def pack(before, after, address, matrix_address):
    """Create compact private reference: one SHA-256 per 4-KiB RAM block."""
    if (not isinstance(before, bytes) or not isinstance(after, bytes) or
            not isinstance(address, int) or type(address) is not int or
            type(matrix_address) is not int or address < 0 or
            not 18 <= len(before) <= MAX_BYTES or len(before) != len(after) or
            address + len(before) > 0x100000000 or
            not address <= matrix_address or matrix_address + 18 > address + len(before)):
        raise ValueError('invalid before/after RAM capture')
    return {
        'address': address,
        'size': len(after),
        'block_size': BLOCK_SIZE,
        'block_sha256': [hashlib.sha256(after[i:i+BLOCK_SIZE]).hexdigest()
                         for i in range(0, len(after), BLOCK_SIZE)],
        'expected_changed_bytes_outside_matrix': changed_outside_matrix(
            before, after, address, matrix_address),
    }


def decode(raw, matrix_address):
    """Fail closed on malformed or incomplete private memory reference."""
    if not isinstance(raw, dict) or set(raw) != {
            'address', 'size', 'block_size', 'block_sha256',
            'expected_changed_bytes_outside_matrix'}:
        raise ValueError('invalid full-memory reference keys')
    address, size, block_size = (raw[key] for key in ('address', 'size', 'block_size'))
    expected_changes = raw['expected_changed_bytes_outside_matrix']
    if (any(type(x) is not int for x in (address, size, block_size, expected_changes))
            or address < 0 or not 18 <= size <= MAX_BYTES or
            address + size > 0x100000000 or block_size != BLOCK_SIZE or
            not 0 <= expected_changes <= size or
            not address <= matrix_address or matrix_address + 18 > address + size):
        raise ValueError('invalid full-memory range or change count')
    hashes = raw['block_sha256']
    if not isinstance(hashes, list) or len(hashes) != (size+BLOCK_SIZE-1)//BLOCK_SIZE:
        raise ValueError('incomplete final RAM block hashes')
    if any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h)
           for h in hashes):
        raise ValueError('malformed final RAM block checksum')
    return {'address':address, 'size':size, 'hashes':tuple(hashes),
            'expected_changed_bytes_outside_matrix':expected_changes}


def snapshot(memory, address, size):
    """Read contiguous mapped memory efficiently, across EXE-overlay boundaries.

    A memory gap raises rather than inventing zero bytes. This method depends
    only on the MappedMemory's public ``regions`` mapping, not the game code.
    """
    if size > MAX_BYTES or size < 1:
        raise ValueError('invalid RAM snapshot size')
    pieces = []
    cursor, end = address, address + size
    for base, region, _ in sorted(memory.regions, key=lambda x:x[0]):
        if cursor == end:
            break
        if base > cursor:
            raise ValueError('guest RAM snapshot contains unmapped gap')
        last = base + len(region.data)
        if last <= cursor:
            continue
        copy_end = min(last, end)
        pieces.append(bytes(region.data[cursor-base:copy_end-base]))
        cursor = copy_end
    if cursor != end:
        raise ValueError('guest RAM snapshot is not fully mapped')
    return b''.join(pieces)


def compare(memory, expected, before, *, guest_stopped_at_expected_pc,
            matrix_address):
    """Validate exact final RAM by chunk and external mutation count."""
    if type(guest_stopped_at_expected_pc) is not bool:
        raise ValueError('invalid stop evidence')
    if not isinstance(expected, dict) or not isinstance(before, bytes):
        raise ValueError('invalid memory comparison inputs')
    address, size = expected['address'], expected['size']
    if len(before) != size:
        raise ValueError('missing complete captured before RAM range')
    # After an incomplete run, do not offer speculative mismatch locations.
    if not guest_stopped_at_expected_pc:
        return {'comparison_performed':False, 'matches_reference':False,
                'checked_block_count':None, 'mismatching_block_indices':[],
                'expected_changed_bytes_outside_matrix':None,
                'observed_changed_bytes_outside_matrix':None,
                'changed_byte_count_outside_matrix_matches':None,
                'external_ps1_hardware_authenticated':False,
                'private_values_emitted':False}
    after = snapshot(memory, address, size)
    bad = [i for i,(offset, digest) in enumerate(zip(
        range(0, size, BLOCK_SIZE), expected['hashes']))
        if hashlib.sha256(after[offset:offset+BLOCK_SIZE]).hexdigest() != digest]
    observed = changed_outside_matrix(before, after, address, matrix_address)
    expected_changed = expected['expected_changed_bytes_outside_matrix']
    return {'comparison_performed':True, 'matches_reference':not bad and observed == expected_changed,
            'checked_block_count':len(expected['hashes']),
            'mismatching_block_indices':bad,
            'expected_changed_bytes_outside_matrix':expected_changed,
            'observed_changed_bytes_outside_matrix':observed,
            'changed_byte_count_outside_matrix_matches':observed == expected_changed,
            'external_ps1_hardware_authenticated':False,
            'private_values_emitted':False}
