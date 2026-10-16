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
