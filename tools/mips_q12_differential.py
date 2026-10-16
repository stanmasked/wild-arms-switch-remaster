"""Differential test harness for synthetic LH/MULT/MFLO/SRA/SH schedules.

Independent reference arithmetic is checked against the MIPS executor's
actual signed halfword reads, multiply, arithmetic shift and halfword stores.
No original Wild Arms executable, lookup table or coefficient data is needed.
"""
import struct

from .mips_control_flow import execute
from .mips_matrix_memory import MappedMemory, matrix_coefficients
from .mips_q12_arithmetic_reference import sh_q12_product, sh_q12_dot3

CODE = 0x80010000
LEFT = 0x80100000
RIGHT = 0x80100100
MATRIX = 0x80100200


def instr(opcode, rs=0, rt=0, immediate=0):
    return ((opcode << 26) | (rs << 21) | (rt << 16) |
            (immediate & 0xffff))


def special(function, rs=0, rt=0, rd=0, shift=0):
    return ((rs << 21) | (rt << 16) | (rd << 11) |
            (shift << 6) | function)


def build_nine_product_program():
    """Nine distinct LH pairs -> MULT -> MFLO -> SRA -> SH operations."""
    words = []
    for slot in range(9):
        offset = slot * 2
        words += [instr(33, 16, 8, offset),       # LH t0, offset(s0)
                  instr(33, 17, 9, offset),       # LH t1, offset(s1)
                  0,                              # R3000A LW/LH delay
                  special(24, 8, 9),              # MULT t0,t1 (signed)
                  special(18, rd=10),             # MFLO t2
                  special(3, rt=10, rd=10, shift=12),
                  instr(41, 5, 10, offset)]       # SH t2, offset(a1)
    return tuple(words)


def build_nine_dot3_program(*, shift_each=False):
    """Nine three-term dot products. Choose precise shift placement."""
    words = []
    for slot in range(9):
        words.append(instr(9, 0, 11, 0))  # ADDIU t3,$zero,0 (accumulator)
        for term in range(3):
            offset = 2 * (slot * 3 + term)
            words += [instr(33, 16, 8, offset),
                      instr(33, 17, 9, offset), 0,
                      special(24, 8, 9),
                      special(18, rd=10)]
            if shift_each:
                words.append(special(3, rt=10, rd=10, shift=12))
            words.append(special(33, rs=11, rt=10, rd=11))  # ADDU
        if not shift_each:
            words.append(special(3, rt=11, rd=11, shift=12))
        words.append(instr(41, 5, 11, 2 * slot))
    return tuple(words)


def replay(words, left, right):
    """Return 9 signed halfword outputs; fail on any incomplete guest replay."""
    if len(left) != len(right) or len(left) not in (9, 27):
        raise ValueError('expected nine or 27 signed-halfword inputs')
    if any(not isinstance(value, int) or not 0 <= value <= 65535
           for value in (*left, *right)):
        raise ValueError('operands must be unsigned 16-bit memory halfwords')
    image = struct.pack('<%dI' % len(words), *words)
    raw_left = struct.pack('<%dH' % len(left), *left)
    raw_right = struct.pack('<%dH' % len(right), *right)
    memory = (MappedMemory().map_region(CODE, image)
              .map_region(LEFT, raw_left)
              .map_region(RIGHT, raw_right)
              .map_region(MATRIX, bytes(18), writable=True))
    registers = [0] * 32
    registers[16], registers[17], registers[5] = LEFT, RIGHT, MATRIX
    trace = execute(image, CODE, CODE, memory, registers,
                    max_steps=len(words) + 1)
    if not trace['completed'] or trace['reason'] != 'end_of_image':
        raise RuntimeError('synthetic MIPS arithmetic did not complete')
    if len(trace['store_addresses']) != 9:
        raise RuntimeError('incomplete synthetic nine-coefficient matrix')
    return matrix_coefficients(memory, MATRIX)


def reference_product_outputs(left, right):
    if len(left) != len(right) or len(left) != 9:
        raise ValueError('expected nine pairs')
    return tuple(_as_signed16(sh_q12_product(a, b))
                 for a, b in zip(left, right))


def reference_dot3_outputs(left, right, *, shift_each=False):
    if len(left) != len(right) or len(left) != 27:
        raise ValueError('expected 27 pairs')
    return tuple(_as_signed16(sh_q12_dot3(
        left[n:n+3], right[n:n+3], shift_each=shift_each))
        for n in range(0, 27, 3))


def _as_signed16(value):
    return value - 65536 if value & 32768 else value
