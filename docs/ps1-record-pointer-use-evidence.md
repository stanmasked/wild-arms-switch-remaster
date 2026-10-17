# Stage 233 — static post-index pointer-use signatures (read-only)

Stage 232 independently confirmed that the **checked-in** eleven-word
MIPS signature computes an index coefficient of 2708, not the earlier
claimed 364. Neither number was authenticated as an original Wild Arms
record size or a PlayStation runtime trace.

Stage 233 adds `tools/audit_record_pointer_use.py` to inspect the **ten
words following that signature** in each of three previously listed
function windows. It requires an exact signature and a complete bounded
window at **all three** locations before publishing counts; mismatch at
one site produces an error and no partial site report.

The deliberately small straight-line parser accepts only literal NOPs,
either `addu v1,v1,v0` or `addu v1,v0,v1`, then a direct PS1 load/store
using `v1` as its base. If there is a branch, jump, call, intervening
unrecognized instruction, memory access before the add, or a missing
window, the sequence remains **unresolved**. It does not follow control
flow, prove address uniqueness, emulate load delays, infer a field
layout, or verify actual access on PS1 hardware.

## Overlapping function windows

Two investigated entry points are only 76 bytes apart while the
conservative per-site inspection window spans 84 bytes. Accordingly,
the second window can encounter the next function's index prefix.
This **must not** be misreported as a clean straight-line pointer
addition without an access. The analyzer treats those intervening
non-NOP instructions as unresolved. A specific synthetic overlap
regression ensures the uncertainty remains visible. This is a
window-shape limitation, not proof that either target actually
executes into the next function.

## Run privately on user-owned source data

```sh
python3 -m tools.audit_record_pointer_use \
  /private/WildArms.bin /private/disc-inventory.json
```

The same private raw MODE2/Form1 disc and local `inspect_disc.py --json`
inventory format used in prior stages apply. Never publish game images,
executable sections, proprietary assets, traces, private debugger
registers or RAM dumps.

The output includes only the three-site count, committed opcode-derived
coefficient, numbers of **syntactic** patterns with direct v1-based
memory use, syntactic additions without such use, and unresolved
post-index sequences; all hardware and record-size attestation flags
remain false. There are no target PCs, per-site labels, raw opcode
values, private field offsets, or memory contents. Errors are generic.

Synthetic tests cover direct and reversed operand forms, NOP, load,
store, branches, mutations, pre-add memory, missing windows, bounded
input, and sanitized CLI output. This narrows **where an authentic
debugger trace is needed**, but a genuine original game's record
length can only be stated after the authentic EXE/code signatures,
executed control flow, pointer origin, and multiple index-address
differences are independently observed. The code in the repository
contains **no authentic PlayStation trace**.

### Important MIPS pipeline boundary

The recognized prefix includes `lw v1, offset(v1)` followed by
`sll v0,v0,2`. A subsequent `addu` at the first tail instruction
can consume the earlier loaded value under the standard one-instruction
load-delay model, because the intervening SLL has already executed.
But without proving the executed path, the observed syntactic adjacency
alone cannot establish that this particular pointer addition ran.

The independent 88-byte initializer documented in
`tools/verify_indexed_init_call.py` remains a different code site and
record domain. Do not combine its 88-byte coefficient with 2708 or
the unsupported legacy 364-byte claim.
