"""Independent integer oracle for explicitly defined *synthetic* PS1 Q12 schedules.

Not a reconstruction of the actual Wild Arms matrix builder. Inputs represent
signed 16-bit fixed-point operands, products follow 32-bit MIPS LO wrapping,
SRA is arithmetic by twelve, and SH preserves only the low sixteen bits.

This module intentionally does not import the emulator's fixed32 helpers.
"""

Q12_SHIFT = 12
U16_MASK = (1 << 16) - 1
U32_MASK = (1 << 32) - 1


def signed16(bits):
    """Interpret a 16-bit memory halfword in two's-complement representation."""
    if not isinstance(bits, int) or not 0 <= bits <= U16_MASK:
        raise ValueError('expected an unsigned 16-bit halfword')
    return bits - 0x10000 if bits & 0x8000 else bits


def signed32(bits):
    """Independent two's-complement interpretation of a MIPS register."""
    bits &= U32_MASK
    return bits - 0x100000000 if bits & 0x80000000 else bits


def mult_hi_lo(rs, rt, *, signed=True):
    """Return (HI, LO) for 32x32 -> 64-bit MULT/MULTU, as unsigned words."""
    left = signed32(rs) if signed else rs & U32_MASK
    right = signed32(rt) if signed else rt & U32_MASK
    word64 = (left * right) % (1 << 64)
    return (word64 >> 32) & U32_MASK, word64 & U32_MASK


def sh_q12_product(a_bits, b_bits):
    """Oracle for LH a; LH b; MULT; MFLO; SRA 12; SH (unsigned SH bits)."""
    a, b = signed16(a_bits), signed16(b_bits)
    product = (a * b) & U32_MASK  # MIPS MFLO discards HI
    return (signed32(product) >> Q12_SHIFT) & U16_MASK


def sh_q12_dot3(a_bits, b_bits, *, shift_each=False):
    """Three signed-LH products with 32-bit ADDU and SH truncation.

    With shift_each=False: accumulate *raw* MFLO products modulo 2^32,
    then arithmetic SRA 12 once. With shift_each=True: SRA each MFLO
    before wrapping ADDU. They can differ for negatives/overflow.
    """
    if len(a_bits) != 3 or len(b_bits) != 3:
        raise ValueError('expected exactly three signed halfword operands per side')
    terms = [(signed16(a) * signed16(b)) & U32_MASK
             for a, b in zip(a_bits, b_bits)]
    if shift_each:
        shifted = [(signed32(term) >> Q12_SHIFT) & U32_MASK for term in terms]
        total = sum(shifted) & U32_MASK
    else:
        total = sum(terms) & U32_MASK
        total = (signed32(total) >> Q12_SHIFT) & U32_MASK
    return total & U16_MASK
