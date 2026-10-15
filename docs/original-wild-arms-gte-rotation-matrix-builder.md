# Original Wild Arms: constructor of the GTE rotation matrix

The user-owned PS-X `WILDARMS.EXE` was inspected locally, with load address `0x80011420`. Game binaries and assets have not been uploaded or committed.

## New original-code evidence

In the polygon preparation function, **`JAL 0x800B7118` at `0x80077980`** receives `a1 = sp + 16` (assigned at `0x80077970`). The callee builds the rotation matrix into this stack buffer. Immediately afterward, **`JAL 0x800B6DD8` at `0x80077988`** loads the resulting five 32-bit packed words into the GTE rotation-matrix control registers 0–4.

The constructor function `0x800B7118 … 0x800B739C` contains **10 `SH` writes to `a1`**, collectively covering every two-byte offset in a nine-coefficient 3×3 matrix:

| Matrix coefficient slot | Destination offsets (relative to a1) |
|---|---|
| 1–3 | +0, +2, +4 |
| 4–6 | +6, +8, +10 |
| 7–9 | +12, +14, +16 |

The offset **+16** is written by two separate instruction sites (`0x800B7214` and `0x800B7254`). The complete set of unique destinations is `0,2,4,6,8,10,12,14,16`. Branches may select different writes; the bounded linear static scan does not prove both occur in any one execution.

**Correction based on subsequent local EXE verification:** `0x800CBE44` is the base address of a directly indexed, 4096-entry packed sine/cosine table inside the executable's load image; it is **not a global pointer slot**. The six indexed `LW` instructions are `0x800B7140`, `0x800B7168`, `0x800B71A4`, `0x800B71CC`, `0x800B7230`, and `0x800B7264`. Each reads a table word at `0x800CBE44 + 4 * angle_index`. The table contains signed 16-bit sine and cosine samples at approximately Q12 scale. Exact branch-dependent coefficient selection and the original table-generation algorithm remain unproven. See `docs/original-wild-arms-gte-trig-table.md`.

This establishes a reproducible high-level chain:

```text
JAL 0x800B7118 (matrix construction, a1=sp+16)
  -> nine 16-bit coefficient slots
JAL 0x800B6DD8 (matrix loader, a0=sp+16)
  -> GTE control registers 0–4
JAL 0x800B68E8 (geometry helper)
  -> GTE MVMVA rotation × V0
  -> IR1, IR2, IR3 stored into output memory
```

The constructor is statically located before the rotation loader, but dynamic matrix coefficients and branch-path effects are not established.

## Verification

```sh
python3 tools/audit_gp0_rotation_matrix_builder.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The original EXE audit reported `builder_called=true`, `a1_is_stack_plus_16=true`, `complete_matrix_slots=true`, six indexed table loads and `runtime_coefficients_recovered=false`. Twelve unit tests cover SH decoding, unique and duplicate slots, correct stack pointer and JAL, signed LUI/LW address formation, false-positive rejections and invalid ranges.

The full local host CMake/C++20 build passed **48/48 CTest suites**. This is static reverse engineering and host test verification; it is not a native playable Switch port or hardware-accurate GTE certification.

Next trace the table pointer at `0x800CBE44`, its indexing arithmetic and the branch paths that select coefficient writes. Only then infer the mathematical representation and test it against the existing C++ GTE reference.
