# Stage410 — independent MIPS code corroboration for CDFLR base

## Scope

Read-only local examination of the user's original `WILDARMS.EXE` (PS-X EXE). The byte-level source remains private; GitHub contains only a semantic MIPS instruction-pattern analyzer and synthetic tests. No executable code is run.

## Direct machine-code observations

Two consecutive-instruction `lui/ori` constructors for `0x80183000` were observed inside the bounded declared executable text region:

1. **File offset `0x58AEC`:** `lui a1,0x8018; ori a1,a1,0x3000`. Nearby code sets `a2 = 0x0003A000` and invokes a `jal` subroutine at runtime address `0x8002356C`. In MIPS calling-convention terms, the candidate buffer address and byte count are arguments to that call. Its callee and relationship to the named disc file still require independent confirmation.
2. **File offset `0x58B4C`:** sets destination `0x80183000`, source `0x80200000`, and source end `0x8023A000`. A bounded loop loads four 32-bit words at a time and stores them to the destination, increments both pointers by 16 bytes, and branches back until the source reaches the end. The copy length is thus **`0x3A000` = 237,568 bytes**, or **14,848** sixteen-byte iterations.

The original `CDFLR.BIN` pointer header gives the same `0x80183000` candidate base when interpreting its first target as file offset `0x100`. The main executable also contains one aligned data literal with that address at offset `0xC1B40`. Code-level use of the address is much stronger corroboration than the literal alone, **but this does not yet prove that the copied buffer actually comes from CDFLR.BIN**.

## Reproducing the non-executing audit

```sh
python tools/audit_cdflr_loader_code.py /private/path/WILDARMS.EXE \
  > /private/path/loader-code-evidence.json
```

The analyzer checks the native PS-X EXE header and bounded text extent, looks for exact structural instruction patterns, and emits only file offsets, sizes, call-target metadata and booleans. It does not output opcodes, code bytes, source strings or game graphics.

## Next proof gates

- Trace what sets the first call's `a0` argument and what the `0x8002356C` subroutine does, without assuming it is the CDFLR file reader.
- Correlate the copied region with CDFLR header/record offsets, ideally through a reference emulator memory trace.
- Determine whether the alternating 512-byte/payload regions in CDFLR are genuine PS1 CLUT/image pairs, using bounded decoding and an actual reference capture.
- Keep record #25 in CDSTG separate from normal PS-X EXE-like overlays.

CI must use synthetic instruction streams only; no original game assets or full executable disassembly in public workflow artifacts.
