#!/usr/bin/env python3
"""Execute a strictly supported subset of PS1 MIPS integer instructions.

No memory, branches, load delays or GTE operations. Unsupported instructions
raise ValueError rather than silently corrupting concrete register values.
"""
try:
    from .mips_fixed32 import u32,sign_extend16,mult,sll,srl,sra,add32,sub32,addiu,slt
except ImportError:
    from mips_fixed32 import u32,sign_extend16,mult,sll,srl,sra,add32,sub32,addiu,slt


def step(word, gpr, hi=0, lo=0):
    if len(gpr)!=32:
        raise ValueError('expected 32 GPR values')
    regs=[u32(x) for x in gpr]
    op=(word>>26)&63
    rs=(word>>21)&31
    rt=(word>>16)&31
    rd=(word>>11)&31
    sa=(word>>6)&31
    fn=word&63
    imm=word&65535
    hi,lo=u32(hi),u32(lo)
    if word==0:
        pass
    elif op==0:
        if fn in (0,2,3) and rs==0:
            regs[rd]={0:sll,2:srl,3:sra}[fn](regs[rt],sa)
        elif fn in (4,6,7) and sa==0:
            regs[rd]={4:sll,6:srl,7:sra}[fn](regs[rt],regs[rs]&31)
        elif fn in (24,25) and rd==0 and sa==0:
            hi,lo=mult(regs[rs],regs[rt],signed=fn==24)
        elif fn in (16,18) and rs==0 and rt==0 and sa==0:
            regs[rd]=hi if fn==16 else lo
        elif fn in (17,19) and rt==0 and rd==0 and sa==0:
            if fn==17: hi=regs[rs]
            else: lo=regs[rs]
        elif fn in (32,33,34,35,36,37,38,39,42,43) and sa==0:
            a,b=regs[rs],regs[rt]
            if fn in (32,33): regs[rd]=add32(a,b,fn==32)[0]
            elif fn in (34,35): regs[rd]=sub32(a,b,fn==34)[0]
            elif fn==36: regs[rd]=a&b
            elif fn==37: regs[rd]=a|b
            elif fn==38: regs[rd]=a^b
            elif fn==39: regs[rd]=u32(~(a|b))
            else: regs[rd]=slt(a,b,unsigned=fn==43)
        else: raise ValueError('unsupported SPECIAL instruction')
    elif op in (8,9):
        regs[rt]=add32(regs[rs],sign_extend16(imm),op==8)[0]
    elif op in (10,11):
        regs[rt]=slt(regs[rs],sign_extend16(imm),unsigned=op==11)
    elif op in (12,13,14):
        value=imm
        regs[rt]=({12:lambda a,b:a&b,13:lambda a,b:a|b,
                   14:lambda a,b:a^b}[op])(regs[rs],value)
    elif op==15 and rs==0:
        regs[rt]=imm<<16
    else:
        raise ValueError('unsupported opcode or transfer')
    regs[0]=0
    return tuple(regs),hi,lo
