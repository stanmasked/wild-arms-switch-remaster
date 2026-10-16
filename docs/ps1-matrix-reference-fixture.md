# Stage 211 — private PS1 matrix numeric reference comparison

This host tool compares nine signed 16-bit matrix coefficients against an **independently supplied reference**. It does not include or distribute original game assets.

## Run locally

```sh
python3 -m tools.audit_ps1_matrix_reference --exe /private/WILDARMS.EXE \
  --reference /private/ps1-matrix-capture.json
```

Expected private JSON schema (placeholders are **not** a valid capture):

```json
{
  "schema": "wild-arms-ps1-matrix-reference-v1",
  "source": "external_ps1_capture_claim",
  "exe_sha256": "<64 lowercase hex characters of full EXE SHA-256>",
  "entry_pc": "0x800b7118",
  "stop_pc": "0x80077988",
  "matrix_address": "0x80110000",
  "gpr": ["<all 32 unsigned 32-bit GPR values, numbered 0-31>"],
  "hi": "0x00000000",
  "lo": "0x00000000",
  "pending_load": null,
  "in_branch_delay_slot": false,
  "max_steps": 4096,
  "memory_segments": [{"address": "0x80000000", "data_hex": "<private RAM bytes in hex>"}],
  "expected_matrix_s16": [0,0,0,0,0,0,0,0,0]
}
```

The sample addresses and zeros are illustrative only. An actual PS1 capture must supply the debugger's **exact instruction-boundary state**: full GPRs, HI/LO, entry PC, RAM/stack/Q12 data referenced by the builder, real matrix output pointer, return/stop PC *after* the final executed SH and JR delay slot, and nine observed **signed** coefficients from that same original-game run. SHA-256 must refer to the precise extracted PS-X EXE before RAM overlay. No missing register or RAM byte is silently populated with synthetic data. Register 0 must equal zero.

`memory_segments` are hexadecimal snapshots of writable guest RAM. A segment can cover all 2 MiB PS1 RAM and overlap or straddle the load-image boundary; the verifier overlays EXE RAM bytes and maps the rest. Segments cannot overlap each other. Total explicit snapshot bytes must not exceed 4 MiB. Matrix buffer must be mapped; `entry_pc` must lie in the image. The source value `external_ps1_capture_claim` is **an unverified declaration**, not an authenticated PS1 observation; use `synthetic` for generated fixtures.

The tool first validates the EXE hash, then runs a bounded MIPS interpreter with the **supplied** state. It checks that execution completed at the **supplied stop PC** and that each of nine final matrix halfwords was written by `SH` (later overlapping SB/SW invalidates it). Only then does it compare nine signed coefficients. The JSON reports the number of matches and mismatching **slot indices**, never guest addresses, registers, original bytes, or coefficient values. Exit code: 0 for 9 matches, 1 for mismatch/incomplete guest run, 2 for invalid input (generic safe JSON error). Keep all captured assets outside GitHub and outside shared logs.

## Limitations

The interpreter is **not** a cycle-exact PS1 emulator: it omits GTE, DMA, interrupts, many CPU corner cases, RAM mirroring and **runtime self-modifying code**. The captured RAM may overlay initial code bytes, but subsequent code writes cannot modify its instruction stream. Matching a user-supplied reference does **not** independently establish hardware provenance, genuine Wild Arms gameplay input, original PS1 equivalence, or a working native Switch port. Report fields `external_ps1_capture_authenticity_independently_verified`, `original_playstation_hardware_equivalence_proven`, `guest_code_mutation_modeled`, `native_switch_port_proven`, and `private_values_emitted` remain false.

Stage 211 adds 31 synthetic tests, including independent Q12 signed-multiply-oracle comparisons, incomplete and overwritten matrix slots, mismatches, SHA checks, invalid/partial memory, executable-memory overlays, entire RAM segments spanning code, and private CLI behavior. No original Wild Arms executable or captured PS1 state is included.

## Stage 213 capture migration

External reference claims must explicitly declare the two pipeline
fields `pending_load` and `in_branch_delay_slot` (see
`docs/ps1-debugger-capture-pack.md`). An absent field is never
treated as a proven empty pipeline for an external capture. Legacy
**synthetic** fixtures may still omit them and default to no pending
load for backward-compatible host tests.

`pending_load` is either `null` or an object containing exactly
`{"gpr": 8, "value_u32": "0x00001000"}`-shaped fields with the true
pending destination and result. Captured GPRs retain the **old**
value before this load has retired. Branch-delay-slot entry is
not yet supported: `in_branch_delay_slot: true` refuses comparison.
Unknown pipeline state must be recaptured at a safe boundary, not
silently guessed.

The comparator exposes only
`initial_load_pipeline_state_explicit` and
`initial_pending_load_applied` booleans; it does not include the
pending target or value in its public summary.
