"""Conservative straight-line provenance for arguments at a MIPS JAL site.

Never emits original opcode bytes, numeric constants, addresses, or register
values. Static window does NOT prove that the window was executed at runtime.
"""
import struct
from dataclasses import dataclass

MASK32 = 0xffffffff


@dataclass(frozen=True)
class Origin:
    roots: frozenset = frozenset()
    loads: frozenset = frozenset()
    constant: object = None
    sp_offset: object = None
    incoming: object = None


def initial_gprs():
    regs = [Origin(roots=frozenset({i}), incoming=i,
                   sp_offset=0 if i == 29 else None) for i in range(32)]
    regs[0] = Origin(constant=0)
    return regs


def sign16(x):
    x &= 0xffff
    return x - 0x10000 if x & 0x8000 else x


def merged(a, b, const=None, sp_offset=None):
    return Origin(a.roots | b.roots, a.loads | b.loads,
                  constant=const, sp_offset=sp_offset)


def add(a, b, subtract=False):
    c = None
    if a.constant is not None and b.constant is not None:
        c = (a.constant + (-b.constant if subtract else b.constant)) & MASK32
    sp = None
    if a.sp_offset is not None and b.constant is not None:
        sp = a.sp_offset + (-b.constant if subtract else b.constant)
    elif not subtract and b.sp_offset is not None and a.constant is not None:
        sp = b.sp_offset + a.constant
    return merged(a, b, c, sp)


def imm_constant(n):
    return Origin(constant=n & MASK32)


def _step(word, regs, pending, hi, lo, at_call=False):
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    sa, fn = (word >> 6) & 31, word & 63
    imm = sign16(word)
    write, new_value, next_load = None, None, None
    a, b = regs[rs], regs[rt]
    if at_call:
        if op != 3:
            raise ValueError('expected JAL')
        write, new_value = 31, imm_constant(0)  # Only provenance, not RA bytes.
    elif word == 0:
        pass
    elif op == 0:
        if fn in (0, 2, 3) and rs == 0:
            write = rd
            const = None
            if b.constant is not None:
                val = b.constant
                if fn == 0: const = val << sa & MASK32
                elif fn == 2: const = val >> sa
                else:
                    val = val if val < (1<<31) else val - (1<<32)
                    const = (val >> sa) & MASK32
            new_value = Origin(b.roots, b.loads, const)
        elif fn in (32, 33, 34, 35) and sa == 0:
            write, new_value = rd, add(a, b, subtract=fn in (34, 35))
        elif fn in (4, 6, 7) and sa == 0:
            write = rd
            new_value = merged(a, b)
        elif fn in (42, 43) and sa == 0:
            write = rd
            const = None
            if a.constant is not None and b.constant is not None:
                left = a.constant if fn == 43 or a.constant < (1<<31) else a.constant - (1<<32)
                right = b.constant if fn == 43 or b.constant < (1<<31) else b.constant - (1<<32)
                const = int(left < right)
            new_value = merged(a, b, const)
        elif fn in (36, 37, 38, 39) and sa == 0:
            write = rd
            const = None
            if a.constant is not None and b.constant is not None:
                if fn == 36: const = a.constant & b.constant
                if fn == 37: const = a.constant | b.constant
                if fn == 38: const = a.constant ^ b.constant
                if fn == 39: const = ~(a.constant | b.constant) & MASK32
            new_value = merged(a, b, const)
        elif fn in (24, 25) and rd == 0 and sa == 0:
            hi = lo = merged(a,b)
        elif fn in (16, 18) and rs == 0 and rt == 0 and sa == 0:
            source = hi if fn == 16 else lo
            if source is None:
                raise ValueError('HI/LO value not established in this window')
            write, new_value = rd, source
        elif fn in (17, 19) and rt == 0 and rd == 0 and sa == 0:
            if fn == 17: hi = a
            else: lo = a
        else:
            raise ValueError('unsupported SPECIAL')
    elif op in (8, 9):
        write, new_value = rt, add(a, imm_constant(imm))
    elif op in (10, 11, 12, 13, 14):
        write = rt
        operand = imm_constant(imm if op in (10, 11) else word & 65535)
        const = None
        if a.constant is not None:
            if op in (10, 11):
                left = (a.constant if op == 11 or a.constant < (1<<31)
                        else a.constant - (1<<32))
                right = (operand.constant if op == 11 or operand.constant < (1<<31)
                         else operand.constant - (1<<32))
                const = int(left < right)
            elif op == 12: const = a.constant & operand.constant
            elif op == 13: const = a.constant | operand.constant
            else: const = a.constant ^ operand.constant
        new_value = merged(a, operand, const)
    elif op == 15 and rs == 0:
        write, new_value = rt, imm_constant((word&65535)<<16)
    elif op in (32,33,35,36,37):
        address = add(a, imm_constant(imm))
        location = ('stack_load' if address.sp_offset is not None
                    else 'absolute_load' if address.constant is not None
                    else 'indirect_load')
        next_load = (rt, Origin(address.roots, address.loads | {location}))
    elif op in (40,41,43):
        pass  # Store reads its source and base but does not write a GPR.
    else:
        raise ValueError('unsupported/control instruction')
    # The immediate following instruction sees the pre-commit registers.
    # A load also supersedes a preceding load aimed at that same GPR.
    if pending and pending[0] != write:
        if pending[0] != 0: regs[pending[0]] = pending[1]
    if write is not None and write != 0:
        regs[write] = new_value
    regs[0] = imm_constant(0)
    return next_load, hi, lo


def _describe(reg, value):
    if value.loads:
        kind = 'memory_derived'
    elif value.incoming is not None:
        kind = 'incoming_gpr'
    elif value.sp_offset is not None:
        kind = 'stack_pointer_derived'
    elif value.constant is not None:
        kind = 'literal_derived'
    else:
        kind = 'computed_gprs'
    return {'gpr':reg, 'source_kind':kind,
            'incoming_gprs':sorted(value.roots),
            'memory_kinds':sorted(value.loads)}


def inspect(image, base, call, lookback_words=4, arguments=(4,5,6,7)):
    """Classify a single pre-JAL straight-line window and its delay slot.

    Never silently crosses another branch or unsupported instruction. The
    output is STATIC evidence only, not confirmed execution at gameplay time.
    """
    if (not isinstance(lookback_words,int) or not 1<=lookback_words<=128
            or call % 4 or base % 4 or len(image)%4
            or not all(isinstance(r,int) and 0<=r<=31 for r in arguments)):
        raise ValueError('invalid JAL window or registers')
    first = call - 4*lookback_words
    if first < base or call+8 > base+len(image):
        return {'window_usable':False,'reason':'window_outside_image',
                'runtime_path_confirmed':False,'arguments':[]}
    regs=initial_gprs()
    hi=lo=None
    pending=None
    for pc in range(first,call+8,4):
        word,=struct.unpack_from('<I',image,pc-base)
        try:
            pending,hi,lo=_step(word,regs,pending,hi,lo,at_call=pc==call)
        except ValueError:
            return {'window_usable':False,'reason':('invalid_call' if pc==call
                                                   else 'unsupported_window_instruction'),
                    'runtime_path_confirmed':False,'arguments':[]}
    # Do not expose a pending load as a completed argument value.
    delayed_gpr = pending[0] if pending and pending[0] else None
    args = []
    for reg in arguments:
        result = _describe(reg,regs[reg])
        if reg == delayed_gpr:
            result['load_pending_at_boundary'] = True
        else:
            result['load_pending_at_boundary'] = False
        args.append(result)
    return {'window_usable':True,'reason':None,
            'runtime_path_confirmed':False,
            'instruction_count':lookback_words+2,
            'arguments':args}
