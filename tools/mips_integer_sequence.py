"""Bounded linear MIPS integer execution. No branching, memory or GTE."""
try:
    from .mips_integer_step import step
    from .mips_fixed32 import u32
except ImportError:
    from mips_integer_step import step
    from mips_fixed32 import u32

def execute(words, gpr=None, hi=0, lo=0, max_steps=4096):
    """Execute known opcodes only; report the first failed instruction."""
    if max_steps < 0:
        raise ValueError('max_steps must be nonnegative')
    if gpr is None:
        gpr = (0,) * 32
    if len(gpr) != 32:
        raise ValueError('expected 32 GPR values')
    regs = tuple([0] + [u32(v) for v in gpr[1:]])
    hi, lo = u32(hi), u32(lo)
    count = 0
    for index, word in enumerate(words):
        if index >= max_steps:
            return {'completed': False, 'reason': 'step_limit', 'index': index,
                    'executed': count, 'gpr': regs, 'hi': hi, 'lo': lo}
        try:
            regs, hi, lo = step(word, regs, hi, lo)
        except (ValueError, OverflowError) as exc:
            return {'completed': False, 'reason': type(exc).__name__,
                    'index': index, 'executed': count,
                    'gpr': regs, 'hi': hi, 'lo': lo}
        count += 1
    return {'completed': True, 'reason': None, 'index': count,
            'executed': count, 'gpr': regs, 'hi': hi, 'lo': lo}
