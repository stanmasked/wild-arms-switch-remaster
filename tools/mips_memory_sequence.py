"""Restricted linear PS1 MIPS load/store interpreter with one load-delay slot.

Not an emulator: no branching, GTE, memory mapping or load/store unaligned variants.
"""
try:
    from .mips_integer_step import step
    from .mips_fixed32 import u32, sign_extend16
except ImportError:
    from mips_integer_step import step
    from mips_fixed32 import u32, sign_extend16

LOADS={32:1,33:2,35:4,36:1,37:2}
STORES={40:1,41:2,43:4}

class Memory:
    def __init__(self, base, data):
        self.base=base
        self.data=bytearray(data)
    def _range(self,addr,size):
        if addr%size: raise ValueError('unaligned memory access')
        off=addr-self.base
        if off<0 or off+size>len(self.data):
            raise ValueError('memory access out of range')
        return off
    def read(self,addr,size,signed=False):
        off=self._range(addr,size)
        return u32(int.from_bytes(self.data[off:off+size],'little',signed=signed))
    def write(self,addr,size,value):
        off=self._range(addr,size)
        self.data[off:off+size]=(value&((1<<(8*size))-1)).to_bytes(size,'little')

def execute(words,memory,gpr=None,hi=0,lo=0,max_steps=4096):
    if max_steps<0: raise ValueError('negative step limit')
    if gpr is None: gpr=[0]*32
    if len(gpr)!=32: raise ValueError('expected 32 registers')
    regs=tuple([0]+[u32(v) for v in gpr[1:]])
    hi,lo=u32(hi),u32(lo)
    pending=None
    executed=0
    for index,word in enumerate(words):
        if index>=max_steps:
            return {'completed':False,'reason':'step_limit','index':index,
                    'executed':executed,'gpr':regs,'hi':hi,'lo':lo,'pending_load':pending}
        op=word>>26
        rs=(word>>21)&31
        rt=(word>>16)&31
        imm=sign_extend16(word)
        next_pending=None
        try:
            if op in LOADS or op in STORES:
                addr=u32(regs[rs]+imm)
                if op in LOADS:
                    value=memory.read(addr,LOADS[op],signed=op in (32,33))
                    next_pending=(rt,value) if rt else None
                else:
                    memory.write(addr,STORES[op],regs[rt])
                updated=regs
            else:
                updated,next_hi,next_lo=step(word,regs,hi,lo)
        except (ValueError,OverflowError) as exc:
            return {'completed':False,'reason':type(exc).__name__,'index':index,
                    'executed':executed,'gpr':regs,'hi':hi,'lo':lo,'pending_load':pending}
        updated=list(updated)
        mask=0
        if op in LOADS or op in (8,9,10,11,12,13,14,15):
            mask=1<<rt
        elif op==0:
            fn=word&63
            if fn in (0,2,3,4,6,7,16,18,32,33,34,35,36,37,38,39,42,43):
                mask=1<<((word>>11)&31)
        if pending is not None:
            dest,value=pending
            if not (mask&(1<<dest)):
                updated[dest]=value
        regs=tuple([0]+updated[1:])
        if op not in LOADS and op not in STORES:
            hi,lo=next_hi,next_lo
        pending=next_pending
        executed+=1
    return {'completed':True,'reason':None,'index':executed,
            'executed':executed,'gpr':regs,'hi':hi,'lo':lo,'pending_load':pending}
