#!/usr/bin/env python3
"""Pure integer reference operations for PS1 MIPS R3000A arithmetic.

No game data. Explicit 32/64-bit masks avoid host-language integer
width and signed-shift differences. ADD/ADDI overflow is reported,
not silently wrapped. This is not a CPU timing model.
"""
MASK32=(1<<32)-1
MASK64=(1<<64)-1

def u32(x):
    return x & MASK32

def s32(x):
    x=u32(x)
    return x-(1<<32) if x & (1<<31) else x

def sign_extend16(x):
    x &= 0xffff
    return x-0x10000 if x & 0x8000 else x

def split64(x):
    x &= MASK64
    return (x>>32)&MASK32, x&MASK32

def mult(rs,rt,signed=True):
    a,b=(s32(rs),s32(rt)) if signed else (u32(rs),u32(rt))
    return split64(a*b)

def sll(rt,shift):
    return u32(u32(rt) << (shift&31))

def srl(rt,shift):
    return u32(rt) >> (shift&31)

def sra(rt,shift):
    return u32(s32(rt) >> (shift&31))

def add32(rs,rt,trap_overflow=False):
    a,b=s32(rs),s32(rt)
    value=a+b
    overflow=not (-(1<<31) <= value <= (1<<31)-1)
    if trap_overflow and overflow:
        raise OverflowError('MIPS signed arithmetic overflow')
    return u32(value),overflow

def sub32(rs,rt,trap_overflow=False):
    value=s32(rs)-s32(rt)
    overflow=not (-(1<<31) <= value <= (1<<31)-1)
    if trap_overflow and overflow:
        raise OverflowError('MIPS signed arithmetic overflow')
    return u32(value),overflow

def addiu(rs,imm16):
    return u32(u32(rs)+sign_extend16(imm16))

def slt(rs,rt,unsigned=False):
    return int((u32(rs)<u32(rt)) if unsigned else (s32(rs)<s32(rt)))
