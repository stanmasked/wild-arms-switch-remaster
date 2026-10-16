# Stage 191 — bounded concrete MIPS branch execution

`tools/mips_control_flow.py` is a host-only replay engine for a restricted
subset of PS1 MIPS **integer** instructions. Unlike the prior linear memory
runner, it fetches code by guest PC, evaluates supported branch predicates
against concrete registers and executes delay slots before redirecting PC.

It supports BEQ/BNE/BLEZ/BGTZ, BLTZ/BGEZ and their branch-likely
variants, J/JAL and JR/JALR. It combines these with existing ADD/ADDIU,
shifts, multiply, HI/LO, aligned LB/LH/LW and SB/SH/SW instructions.
It models a one-instruction load delay: a branch immediately after LW
tests the old register value, while its delay slot sees the loaded value.
Likely branches cancel the delay slot when not taken. Branches appearing
inside a delay slot are explicitly unsupported.

The routine accepts caller-owned loaded code bytes, guest address,
initial GPR state, bounded mapped memory, a finite instruction limit
and optional `stop_pc`. It returns the executed guest PC list, touched
store addresses, final register state and completion/failure status.
**Do not publish raw registers or memory derived from private game
data.** No original executable or texture/audio assets are included.

## Verified synthetic tests

The new `tests/test_mips_control_flow.py` covers nine cases:
taken/not-taken branches, annulled branch-likely slot, an LW-before-BEQ
load hazard, J/JR delay and return, unsupported nested branch,
bounded loops, an unsupported COP2 instruction, and nine matrix
coefficient stores through a jump. The nine-store fixture uses a
synthetic Q12 table and writes the identity 3x3 coefficient matrix
(4096 diagonal, zero elsewhere).

In a local reconstruction of the relevant repository modules,
`python -m unittest discover -s tests -p 'test_mips_*.py'` passed
**25/25** tests (16 prior matrix/trig tests plus 9 new ones).
The tests are registered in host CTest and matrix-audits GitHub Actions.
Successful full GitHub CI remains unverified.

## Explicit limitations

This is **not** validated execution of the game's rotation routine at
`0x800B7118–0x800B739C`. It cannot yet execute GTE/COP2 commands,
external memory mappings, unaligned LWL/LWR/SWL/SWR, all control
instructions, exceptions or exact pipeline timing. Branch-likely
support exists for conservative synthetic experiments; the PlayStation's
MIPS R3000A instruction-set compatibility must be checked before
assuming such opcodes are present in the original executable.

The next validation step is to run bounded traces on a privately
provided, correctly parsed PS-X EXE and report only coverage, stop
reasons and coefficient comparisons, without emitting game bytes.
