"""Disjoint guest-memory regions for private PS1 trig data and matrix output.

The packed table is read-only; the 18-byte matrix buffer is writable.
Neither original game bytes nor decoded table samples are emitted.
"""
from .mips_fixed32 import sign_extend16
from .mips_memory_sequence import Memory
from .mips_trig_memory import ENTRY_BYTES, ENTRY_COUNT

TABLE_ADDRESS = 0x800CBE44
MATRIX_SIZE = 18
MATRIX_OFFSETS = tuple(range(0, MATRIX_SIZE, 2))


class MappedMemory:
    def __init__(self):
        self.regions = []

    def map_region(self, base, data, writable=False):
        length = len(data)
        if not length or base < 0 or base > 0xffffffff or base + length > 0x100000000:
            raise ValueError('invalid mapped region')
        for old_base, old_memory, _ in self.regions:
            if base < old_base + len(old_memory.data) and old_base < base + length:
                raise ValueError('overlapping mapped regions')
        self.regions.append((base, Memory(base, data), bool(writable)))
        return self

    def _region(self, address, size):
        if size not in (1, 2, 4) or address % size:
            raise ValueError('unsupported or unaligned access')
        for base, memory, writable in self.regions:
            if base <= address and address + size <= base + len(memory.data):
                return memory, writable
        raise ValueError('unmapped or cross-region access')

    def read(self, address, size, signed=False):
        memory, _ = self._region(address, size)
        return memory.read(address, size, signed=signed)

    def write(self, address, size, value):
        memory, writable = self._region(address, size)
        if not writable:
            raise ValueError('write to read-only mapped region')
        memory.write(address, size, value)


def prepare_matrix_memory(packed_table, matrix_address, table_address=TABLE_ADDRESS):
    if len(packed_table) != ENTRY_COUNT * ENTRY_BYTES:
        raise ValueError('table must have 4096 packed entries')
    if table_address % 4 or matrix_address % 2:
        raise ValueError('unaligned table or matrix base')
    return (MappedMemory().map_region(table_address, packed_table)
            .map_region(matrix_address, bytes(MATRIX_SIZE), writable=True))


def matrix_coefficients(memory, matrix_address):
    """Nine signed halfword coefficients in original SH layout order."""
    return tuple(sign_extend16(memory.read(matrix_address + offset, 2))
                 for offset in MATRIX_OFFSETS)


def prepare_from_private_exe(blob, matrix_address, table_address=TABLE_ADDRESS):
    """Extract table from caller-owned PS-X EXE in memory; never write it out."""
    try:
        from .audit_original_nclip_winding import parse_exe
    except ImportError:
        from audit_original_nclip_winding import parse_exe
    base, image = parse_exe(blob)
    offset = table_address - base
    size = ENTRY_COUNT * ENTRY_BYTES
    if offset < 0 or offset + size > len(image):
        raise ValueError('packed trig table outside PS-X EXE load image')
    return prepare_matrix_memory(image[offset:offset+size], matrix_address,
                                 table_address=table_address)
