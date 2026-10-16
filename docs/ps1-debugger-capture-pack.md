# Stage 212 — Prepare a private PS1 matrix capture from debugger exports

This **offline, host-only** tool packages two byte-for-byte raw RAM exports and two instruction-boundary register exports into the private `wild-arms-ps1-matrix-reference-v1` JSON expected by the stage-211 numerical comparator. **It does not access a debugger or emulator automatically**, prove the authenticity of a PlayStation recording, or distribute any original game data.

## Record one continuous game session

1. Extract your own `WILDARMS.EXE` from your own copy of the game and retain it privately. Record no proprietary bytes in GitHub issues, actions logs, or commits.
2. Pause the debugger **before executing** the first chosen MIPS instruction (typically the known builder entry `0x800B7118`). Export *all 32 GPRs*, HI/LO and current PC into `before-registers.json`, and export guest RAM bytes to `before-ram.bin` **at that same pause**. `$a1` (GPR 5) is expected to point to the nine halfwords of the matrix; if not, supply the verified `--matrix-address` explicitly.
3. Continue the **same** game session until **after** the ninth matrix SH and the `JR $ra` delay slot have both executed. Pause *before executing* the instruction at the next PC. Export that PC to `after-registers.json` and RAM to `after-ram.bin`, without restarting or changing the game state in between.
4. Export **raw bytes**, *not* a savestate container with a header, compressed sections, or emulator metadata. Both binary RAM files must be the same length. For a 2-MiB physical-RAM dump that corresponds to PS1 KSEG0 virtual addresses, explicitly set `--ram-base 0x80000000`. Do not treat the original physical offset `0x00000000` as the MIPS virtual address; mirrors/aliases are not handled automatically.

The register export format is intentionally emulator-agnostic. Convert your debugger's text or register view to these JSON files **locally**:

`before-registers.json` (example values **placeholders only**):

```json
{
  "schema": "wild-arms-ps1-debugger-registers-v1",
  "pc": "0x800b7118",
  "gpr": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
          0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  "hi": 0,
  "lo": 0,
  "pending_load": null,
  "in_branch_delay_slot": false
}
```

Replace **every** register with the actual captured 32-bit value, especially `$sp`, `$ra`, `$a0`–`$a3` and `$a1` (r5). The fake zeros above are **not** a usable hardware capture. Values may be integers or strings like `"0x80110000"`; PC must be 4-byte aligned.

`after-registers.json`:

```json
{
  "schema": "wild-arms-ps1-debugger-registers-v1",
  "pc": "0x80077988"
}
```

The example stop address is illustrative: **read the actual next PC from the debugger**. It must differ from the before PC and be reached only after the last matrix store.

## Package and optionally compare

```sh
python3 -m tools.audit_ps1_capture_pack \
  --exe /private/WILDARMS.EXE \
  --before-registers /private/before-registers.json \
  --after-registers /private/after-registers.json \
  --before-ram /private/before-ram.bin \
  --after-ram /private/after-ram.bin \
  --ram-base 0x80000000 \
  --output /private/ps1-matrix-capture.json \
  --compare
```

The output reference is a **private local file** containing the full *before* RAM dump as hexadecimal, full *before* registers, and nine signed 16-bit coefficients extracted from the *after* RAM at `$a1` or the explicitly supplied `--matrix-address`. The file is created with restrictive owner-only permissions (0600 on POSIX); an existing output is **never overwritten**. The tool prints only status booleans, safe counts, and (if comparison was requested) mismatch **slot indices**, not memory or coefficient values. `--synthetic` marks test data; otherwise provenance is an **unverified claim** of external PS1 capture.

`--compare` immediately invokes stage 211's bounded guest interpreter using the new JSON; omit it to package first and compare later:

```sh
python3 -m tools.audit_ps1_matrix_reference \
  --exe /private/WILDARMS.EXE \
  --reference /private/ps1-matrix-capture.json
```

Exit status: 0 for package success and, when requested, all nine comparable coefficients matching; 1 for packaged-but-mismatching/incomplete comparison; 2 for invalid capture or output. A mismatching or partial comparison still leaves the private snapshot on disk for further *local* debugging.

## Important validity limits

- The tool cannot certify that before/after files came from the **same play session** or from a PS1. An EXE SHA-256 match establishes only which image was supplied; a purported authentic capture remains unverified.
- RAM must map all nine matrix halfwords in both dumps, and the debugger PC before execution must reside in the supplied EXE load image. For a 2-MiB raw export, make sure it actually covers the needed stack and table locations.
- An instruction boundary after an outstanding `LW/LH` may require pipeline/load-delay state that this format does not record. Prefer a capture boundary with no pending delayed load. The verifier also does not model runtime self-modifying code, RAM mirrors, GTE, DMA, exceptions or interrupts.
- A successful 9/9 result compares against the **user-supplied** after-RAM matrix. It does **not** independently prove the original game's PS1 mathematics or a native Nintendo Switch port.

The new packaging module, CLI and synthetic tests are registered in the host test suite. No real game EXE or debugger exports have been included in this repository.

## Stage 213 — MIPS pipeline status is now mandatory for debugger captures

Starting with stage 213, every **external** PS1 reference and every newly
packed before-registers export must declare both `pending_load` and
`in_branch_delay_slot` explicitly. Existing synthetic-only legacy
references can omit them and default to no pending load. External captures
with either field missing are intentionally rejected.

At a normal instruction boundary with no unresolved load, use:

```json
"pending_load": null,
"in_branch_delay_slot": false
```

If the debugger paused immediately after an `LW`, `LH`, `LB`,
`LHU` or `LBU`, the next instruction still reads the **old** GPR
value. The initial GPR array must contain that old value, and the
separately pending result must be supplied, for example:

```json
"pending_load": {"gpr": 8, "value_u32": "0x00001000"},
"in_branch_delay_slot": false
```

The `gpr` target is 1–31, and `value_u32` is an unsigned 32-bit
value. Do not guess it from the old register: obtain it from the
debugger's pipeline state or choose a safe, later capture boundary
after the load has retired. Never assume a pending value of zero.
If you cannot establish whether a pending load exists, do not
mark `pending_load` null and claim verification.

A capture inside a branch or jump's **delay slot** requires the
unresolved control-transfer target. That state is not modeled in
this snapshot format. Set `in_branch_delay_slot: true` only to
explicitly trigger rejection, then recapture at a supported boundary.
Non-boolean delay-slot declarations are rejected as well.

Two successive loads to the same destination are handled using the
PS1 one-instruction load delay: the earlier load retires after the
second instruction while the second result remains pending. The
numerical comparator emits only booleans about whether pipeline
state was explicit/applied; it never prints the pending register
or value.

These rules apply to the host verifier, not the full Nintendo
Switch game; authentic PS1 gameplay captures and Switch hardware
behavior have not been verified.

## Stage 214 — require an actual completed JR $ra return (recommended)

The stage-211 numerical verifier can now optionally reject a nine-of-nine
coefficient match when the synthetic MIPS replay did **not** actually
complete its final return to the captured stop PC through `JR $ra`.
To enable the stricter, safer capture flow, add `--require-jr-return`
to `tools.audit_ps1_capture_pack`:

```sh
python3 -m tools.audit_ps1_capture_pack \
  --exe /private/WILDARMS.EXE \
  --before-registers /private/before-registers.json \
  --after-registers /private/after-registers.json \
  --before-ram /private/before-ram.bin \
  --after-ram /private/after-ram.bin \
  --ram-base 0x80000000 \
  --output /private/ps1-matrix-capture.json \
  --require-jr-return --compare
```

The packer records `"require_completed_jr_ra": true` in the private
reference JSON. This makes an otherwise matching matrix **ineligible**
unless all the following are verified from executed instruction and
completed-control-transfer evidence:

- The guest stops at the supplied `stop_pc` with reason `stop_pc`.
- The **last** completed guest transfer is a genuine `JR $ra` and
  its destination is exactly that `stop_pc`.
- The return's delay-slot instruction is the **last successfully
  executed instruction**, immediately following the `JR $ra`.
- No pending delayed load remains when the replay reaches the stop.
- Nine final matrix halfwords still have complete successful `SH`
  writes, with no later overlapping stores.

A syntactic `JR $ra`, an earlier return that subsequently executes
more instructions, an unrelated branch, or a stop before the delay
slot do not satisfy this gate. The privacy-safe output includes only
boolean fields under `return_boundary`, plus
`strict_jr_ra_return_required`. It does **not** publish guest PCs,
register contents, matrix values or any memory data.

For older synthetic fixtures, `require_completed_jr_ra` defaults to
false so previously tested artificial straight-line programs still
work. This explicit switch does not prove authentic PS1 hardware,
and the original Wild Arms return path still needs a genuine capture.

## Stage 215 — compare the complete CPU state after the builder

The optional `--require-final-cpu-state` switch (recommended once
the debugger exposes all registers at return) adds a second independent
gate to the nine coefficient and optional completed-JR checks:

```sh
python3 -m tools.audit_ps1_capture_pack \
  --exe /private/WILDARMS.EXE \
  --before-registers /private/before-registers.json \
  --after-registers /private/after-registers.json \
  --before-ram /private/before-ram.bin \
  --after-ram /private/after-ram.bin \
  --ram-base 0x80000000 \
  --output /private/matrix-plus-cpu.json \
  --require-jr-return --require-final-cpu-state --compare
```

With this switch, the **after-registers** JSON must contain a
genuine snapshot of the same session at the supplied **after PC**,
not merely the PC itself. For example (illustrative placeholders,
**not** a real captured state):

```json
{
  "schema": "wild-arms-ps1-debugger-registers-v1",
  "pc": "0x80077988",
  "gpr": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
          0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  "hi": "0x00000000",
  "lo": "0x00000000",
  "pending_load": null,
  "in_branch_delay_slot": false
}
```

The parser requires all 32 unsigned GPR words, unsigned HI/LO,
an explicit pending-load state and a false branch-delay-slot
flag. An incomplete after-register file (e.g. only `gpr`) fails
closed. A PC-only after export remains supported **unless** this
strict mode is requested.

The packed private reference includes
`"require_final_cpu_state": true` and an
`"expected_final_cpu_state"` object with those five state fields
(excluding `pc`, which remains the existing `stop_pc` field).
The bounded interpreter's final CPU state is compared **only** if it
actually reached that stop PC. The separate `final_cpu_state`
summary contains aggregate GPR matches and *indices* of mismatched
GPRs, plus booleans for HI, LO and pending-load equality.
No post-return register words, pending values or RAM bytes appear
in public output.

A new `matches_complete_reference` boolean is the overall result:
it requires all nine comparable coefficients to match, **and**
the final CPU state to match if the strict option was selected.
`matches_supplied_nine_coefficients` keeps its original,
strictly *numerical* meaning. The CLI returns exit status 1 when
the matrix matches but a required final CPU register, HI/LO or
pipeline value does not match.

These checks do **not** independently authenticate the source
of either debugger export, emulate missing GTE/interrupt behavior,
or prove full original-game equivalence or a working Switch port.

## Stage 216 — optional exact after-RAM comparison, including side effects

Add `--require-final-memory-state` to request an exact comparison of
the **entire captured after-RAM range**, not just the nine matrix SH
coefficients and optional CPU state:

```sh
python3 -m tools.audit_ps1_capture_pack \
  --exe /private/WILDARMS.EXE \
  --before-registers /private/before-registers.json \
  --after-registers /private/after-registers.json \
  --before-ram /private/before-ram.bin \
  --after-ram /private/after-ram.bin \
  --ram-base 0x80000000 \
  --output /private/matrix-cpu-and-ram.json \
  --require-jr-return \
  --require-final-cpu-state \
  --require-final-memory-state --compare
```

The packer computes one SHA-256 **per 4096-byte block** of the
full captured after-RAM data and records the count of bytes whose
value changed **outside the known 18-byte matrix**. This compact
reference is saved **only** in the owner-restricted private JSON;
raw after-RAM bytes and block digests are **not** written to the
console or to GitHub.

During replay, the verifier checks that the original before-RAM
range was **fully mapped**, including any EXE-load-image overlap.
A hole is an error; it is never guessed or filled with zeros.
Only after the guest reaches its expected stop PC does the tool
compute final RAM block hashes and compare the net changed-byte
count outside the matrix.

The public result contains only `final_memory_state` booleans,
counts, and the **indices** of 4-KiB blocks that differ. The
`matches_supplied_nine_coefficients` boolean remains solely
numerical; `matches_complete_reference` also requires exact
after-RAM equality if `require_final_memory_state` is enabled.
A side-effect mismatch therefore returns CLI exit code **1** even
if all nine matrix halfwords and the full CPU state match.

A byte written with exactly its previous value cannot be detected
from before/after snapshots alone; this is a **net final-memory**
check, not a trace of all writes, DMA, GTE, or memory-mapped
peripheral interactions. The caller-supplied capture is not
independently authenticated as original PlayStation gameplay.

## Stage 217 — independent debugger store-event trace

**Before/after RAM alone cannot reconstruct the executed store sequence.**
A same-value store or a write that is later undone is invisible in the final
snapshot. Stage 217 therefore accepts a **separate, private** ordered log
exported by the debugger during the same paused-to-paused interval.

Record *every successfully completed* CPU `SB`, `SH` and `SW`,
including temporary writes, same-value writes and stores executed in
a return delay slot. The guest virtual **instruction PC**, resolved
**destination address**, and **width in bytes** (1, 2 or 4) must be exact.
Do not include attempted stores that fault without writing. Preserve
execution order: do not sort or deduplicate the log.

Private `stores.json` example (synthetic placeholders, not real game data):

```json
{
  "schema": "wild-arms-ps1-store-sequence-v1",
  "events": [
    {"pc": "0x80010004", "address": "0x80110000", "width": 2},
    {"pc": "0x80010008", "address": "0x80110002", "width": 2}
  ]
}
```

Collect the event log **directly from an instruction/store trace in
the PS1 debugger**, not by differencing the two RAM exports.
The log currently has a limit of 100,000 successful stores.
The event schema intentionally does not require contents or source
register values; the verifier checks the instruction PC, resolved
address, width and exact event ordering.

To require this check alongside the earlier numeric, CPU and RAM
checks, add these two CLI arguments:

```sh
python3 -m tools.audit_ps1_capture_pack \
  --exe /private/WILDARMS.EXE \
  --before-registers /private/before-registers.json \
  --after-registers /private/after-registers.json \
  --before-ram /private/before-ram.bin \
  --after-ram /private/after-ram.bin \
  --ram-base 0x80000000 \
  --store-events /private/stores.json \
  --require-store-sequence \
  --require-jr-return \
  --require-final-cpu-state \
  --require-final-memory-state \
  --output /private/matrix-cpu-ram-writes.json \
  --compare
```

**Fail-closed:** If `--require-store-sequence` is present but no separate
`--store-events` file is provided, packaging fails. It never fabricates
the log from before/after RAM. An optional log may be supplied without
requiring its match; when the strict switch is set, mismatch makes
`matches_complete_reference` false and the CLI returns 1.

Only aggregate counts for `SB/SH/SW` widths and **up to 32 mismatch
event indices** are emitted in the public `store_sequence` report.
Raw debugger PCs, write addresses and original RAM values are never
printed; those remain in the private owner-restricted reference JSON.
When guest replay fails to reach the expected stop PC, the verifier
withholds mismatch positions. This audit does not authenticate the
origin of an alleged PS1 debugger trace, nor model DMA or unhandled
instructions; all original-game results remain unverified.

## Stage 218 — compare the actual values written by SB, SH and SW

The stage-217 instruction/store log checked **when**, **where** and **how
many bytes** each successful CPU store wrote. Stage 218 adds an
**independent value-bearing trace** collected from the debugger while
the *same* PS1 session executes the bounded builder interval. This
reveals wrong intermediate values even when later stores restore RAM
to the exact expected final state.

Save the private log as `store-values.json`, preserving every
successfully completed `SB`, `SH`, or `SW`, in execution order.
The four fields are: executing instruction `pc`, resolved virtual
`address`, `width` in bytes (1/2/4), and `value_u32` containing
**the exact low 8, 16 or 32 bits actually committed**. Do not export
a sign-extended 32-bit register as the value for `SB` or `SH`;
for example, `SH` from `0xDEADBEEF` records `0x0000BEEF`.
Do not publish the original log.

Synthetic example — these are not observed Wild Arms values:

```json
{
  "schema": "wild-arms-ps1-store-values-v1",
  "events": [
    {"pc": "0x80010004", "address": "0x80110000", "width": 2, "value_u32": "0x00001000"},
    {"pc": "0x80010008", "address": "0x80110002", "width": 1, "value_u32": "0x0000007f"}
  ]
}
```

Compare a genuine private capture with:

```sh
python3 -m tools.audit_ps1_capture_pack \
  --exe /private/WILDARMS.EXE \
  --before-registers /private/before-registers.json \
  --after-registers /private/after-registers.json \
  --before-ram /private/before-ram.bin \
  --after-ram /private/after-ram.bin \
  --ram-base 0x80000000 \
  --store-value-events /private/store-values.json \
  --require-store-values \
  --require-jr-return \
  --require-final-cpu-state \
  --require-final-memory-state \
  --output /private/matrix-cpu-ram-write-values.json \
  --compare
```

`--store-value-events` is **separate** from the earlier
`--store-events` location-only reference. Either can be enabled
independently, or both can be supplied: if both logs disagree
on the store PC, address, width or event order, the entire
reference is rejected as contradictory.

`--require-store-values` prevents a positive
`matches_complete_reference` unless all events match, regardless
of numerical coefficient, final CPU or final RAM equality.
Without this switch, a valid supplied value log is compared
for diagnostics but does not affect the overall result.
The tool **never** infers original intermediate values from
before/after RAM, nor accepts a missing required debugger value log.

The public `store_values` JSON contains only counts, width
histograms, up to 32 mismatch **event indices**, and separate
indices for value versus site mismatches. No written values,
raw PCs, resolved addresses, register values, or secret digests
are emitted. If guest execution stops early, mismatch indices
are withheld. A claimed original PS1 log cannot be independently
authenticated by this workflow. Hardware, DMA, GTE and original
gameplay remain outside this subset executor's verified coverage.
