# Stage 187 — bounded memory and delayed loads

`tools/mips_memory_sequence.py` adds an isolated memory buffer with a
fixed guest-address base, little-endian byte/halfword/word access, bounds
checking and alignment validation. A restricted linear MIPS instruction
runner supports LB/LBU, LH/LHU, LW, SB, SH and SW alongside the existing
integer-step subset.

A loaded register value becomes visible after the following instruction
has read its operands (one-instruction load delay). A following instruction
writing that same register wins. A load at the end of a sequence is returned
as `pending_load`; the result is not silently committed.

Six synthetic tests cover the load delay, write-after-load cancellation,
little-endian halfword store, bounds/alignment errors, signed halfword,
and final pending load. These tests were run on an isolated local harness
with minimal arithmetic stubs (6/6), not on the complete repository.
They are registered in CTest and GitHub Actions; successful full CI remains
unverified.

**Limitations:** no branches, GTE execution, actual original trig-table
mapping, hardware memory aliases, load-interlock hazards or full exception
model. The buffer takes caller-owned bytes only. No `WILDARMS.EXE` or game
asset is embedded or committed.
