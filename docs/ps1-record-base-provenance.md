# Stage 234 — static PS1 base-pointer lineage and conservative BEQ/BNE paths

The earlier record-index audit recognized a **checked-in 2708 coefficient**
and a syntactic post-index `ADDU v1,v1,v0` followed by a `v1`-based load
or store. That is **not an authentic record size** or an executed trace.

This stage adds `tools/audit_record_base_provenance.py` to separately
check the **pointer source** and bound the treatment of common conditional
branches. All evidence remains restricted to static opcode shapes:

- The exact LUI→LW chain sets up `v1` from a global pointer slot in
  memory, but the *contents of that slot are unknown*.
- The immediately following `SLL v0,v0,2` supplies an independent
  instruction between the `LW` and a possible following `ADDU`.
  Under the PS1 one-instruction load-delay convention the first tail
  instruction can consume the loaded pointer on a straight-line path.
  Static code bytes still cannot prove the prefix was executed.
- A bounded graph enumerator handles ordinary non-likely `BEQ` and
  `BNE` with **literal NOP delay slots**. `BEQ r,r` is always taken;
  `BNE r,r` is never taken; otherwise **both alternatives** are explored.
  It allows only forward destinations inside the 10-instruction tail.
- Only a direct index-preserving `ADDU`, optional NOPs, and subsequent
  load/store based on `v1` are accepted as a candidate chain. Every
  unsupported operation, unmodeled delay slot, branch-likely, JR/JALR,
  call, backward branch or out-of-window target is unresolved.
- Equivalent branch states can converge in the static graph without
  being counted as a separate unsupported outcome.

The result counts sites where **all enumerated syntactic paths** reach
a candidate access, where only **some** paths do, and those with no
admissible access. It separately counts examined known/unknown branch
predicates. These are NOT gameplay probabilities, verified field
offsets, pointer values, original PS1 execution evidence, a true record
length, or a Nintendo Switch build. The 88-byte indexed initializer
in another function is deliberately not folded into this analysis.

## Run locally on private user-owned disc data

```sh
python3 -m tools.audit_record_base_provenance \
  /private/WildArms.bin /private/disc-inventory.json
```

The inventory must be a locally generated `inspect_disc.py --json`
listing and the disc must be a valid raw MODE2/Form1 image. No original
game bytes, guest PCs, original register values, memory contents or
individual function windows are emitted. The JSON is only aggregate
counts/booleans. A missing/malformed private image or inventory
produces a generic `invalid_private_input` JSON and exit status **2**,
without leaking exception messages or paths; successful bounded
inspection exits **0**.

Synthetic regressions exercise the matching load chain, BEQ same-reg
taken, BNE same-reg not taken, unknown two-way branches, one unresolved
alternative, mandatory NOP slot, branch-likely refusal, J/JR refusal,
out-of-window and backward targets, convergent paths, corrupted prefix
at one of the three sites, and sanitized CLI output. The matrix audit
workflow runs this suite alongside existing PS1 host tests.

**Verification boundary:** Without an authentic privately captured
executed-PC sequence, inputs, relevant RAM snapshots and observed
address differences for multiple indices, this tool cannot identify
the real in-game base pointer, record boundaries, or structure size.
The old 364-byte claim stays rejected; 2708 is an opcode-derived index
coefficient only. No original PlayStation hardware equivalence has
been established.
