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
  "lo": 0
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
