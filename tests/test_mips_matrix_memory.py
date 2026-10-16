import struct
import unittest
from tools.mips_matrix_memory import (
    TABLE_ADDRESS, MATRIX_OFFSETS, MappedMemory, prepare_matrix_memory,
    matrix_coefficients, prepare_from_private_exe)
from tools.mips_trig_memory import synthetic_cardinal_table
from tools.mips_memory_sequence import execute

MATRIX = 0x80110000


def i(op, rs, rt, immediate):
    return op << 26 | rs << 21 | rt << 16 | (immediate & 65535)


def r(fn, rs=0, rt=0, rd=0, sa=0):
    return rs << 21 | rt << 16 | rd << 11 | sa << 6 | fn


class MatrixMemoryTests(unittest.TestCase):
    def test_identity_coefficients_written_by_mips(self):
        mem = prepare_matrix_memory(synthetic_cardinal_table(), MATRIX)
        registers = [0] * 32
        registers[5] = MATRIX
        registers[8] = TABLE_ADDRESS
        # Load packed (sin=0, cos=4096), respect load delay, extract halves.
        program = [i(35, 8, 10, 0), 0, r(3, rt=10, rd=11, sa=16),
                   r(0, rt=10, rd=12, sa=16), r(3, rt=12, rd=12, sa=16)]
        for offset in MATRIX_OFFSETS:
            program.append(i(41, 5, 11 if offset in (0, 8, 16) else 12, offset))
        result = execute(program, mem, registers)
        self.assertTrue(result['completed'])
        self.assertEqual(matrix_coefficients(mem, MATRIX),
                         (4096, 0, 0, 0, 4096, 0, 0, 0, 4096))

    def test_negative_coefficient_preserves_sign(self):
        mem = prepare_matrix_memory(synthetic_cardinal_table(), MATRIX)
        mem.write(MATRIX + 12, 2, 0xf000)
        self.assertEqual(matrix_coefficients(mem, MATRIX)[6], -4096)

    def test_table_read_only(self):
        mem = prepare_matrix_memory(synthetic_cardinal_table(), MATRIX)
        self.assertEqual(mem.read(TABLE_ADDRESS + 2, 2), 4096)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            mem.write(TABLE_ADDRESS, 2, 0)

    def test_overlapping_regions_rejected(self):
        regions = MappedMemory().map_region(0x1000, bytes(8))
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            regions.map_region(0x1004, bytes(8), writable=True)

    def test_unmapped_and_misaligned_rejected(self):
        mem = prepare_matrix_memory(synthetic_cardinal_table(), MATRIX)
        with self.assertRaises(ValueError):
            mem.read(MATRIX - 2, 2)
        with self.assertRaises(ValueError):
            mem.read(MATRIX + 1, 2)
        with self.assertRaises(ValueError):
            mem.read(MATRIX + 16, 4)

    def test_bad_table_length_and_alignment(self):
        with self.assertRaises(ValueError):
            prepare_matrix_memory(b'', MATRIX)
        with self.assertRaises(ValueError):
            prepare_matrix_memory(synthetic_cardinal_table(), MATRIX + 1)
        with self.assertRaises(ValueError):
            prepare_matrix_memory(synthetic_cardinal_table(), TABLE_ADDRESS)

    def test_synthetic_private_exe_loader(self):
        # This is NOT a copy of the game's EXE; all data are constructed here.
        base = TABLE_ADDRESS - 4
        data = bytes(4) + synthetic_cardinal_table()
        header = bytearray(2048)
        header[:8] = b'PS-X EXE'
        struct.pack_into('<II', header, 0x18, base, len(data))
        mem = prepare_from_private_exe(bytes(header) + data, MATRIX)
        self.assertEqual(mem.read(TABLE_ADDRESS + 2, 2), 4096)

    def test_reject_truncated_original_image(self):
        with self.assertRaises(ValueError):
            prepare_from_private_exe(b'not an exe', MATRIX)

if __name__ == '__main__':
    unittest.main()
