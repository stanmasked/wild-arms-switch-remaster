# Original Wild Arms: callers of GPU polygon cursor initialization

## Static evidence from the original game

Examined the locally held, privately extracted PS-X `WILDARMS.EXE`, loaded at `0x80011420`. The original executable, disc and game assets were **not uploaded to GitHub**.

The preceding cursor-lifecycle audit identified three routines with initializations of the polygon-structure field `+12` using the base address loaded from its `+0` field. In the routine prologues:

- `0x80076910`: `ADDU r17,a0,r0`;
- `0x80076B90`: `ADDU r16,a0,r0`;
- `0x80076F48`: `ADDU r16,a0,r0`.

Therefore the structure base itself comes from each routine's incoming CPU argument `a0`. The new tool `tools/audit_gp0_structure_callers.py` scans the loaded executable for **direct MIPS JAL calls** to these three function entry points and reports the nearest preceding textual assignment to argument register `a0`.

| Cursor-initializer function | Direct JAL address | Most recent pre-call a0 definition | Static argument source |
|---|---|---|---|
| `0x80076908` | `0x80078194` | `0x80078154` | `ADDIU a0,r20,92` |
| `0x80076B88` | `0x80078230` | `0x8007821C` | `ADDIU a0,r20,140` |
| `0x80076F40` | `0x80078370` | `0x80078360` | `ADDU a0,r22,r0` |

Exactly **three direct JAL sites**, one per initializer, were found in the original EXE. The first two structure pointers are offsets **+92** and **+140** from a caller-held pointer `r20`; the third is a copy of `r22`. These are caller-side argument definitions and should **not** be confused with the separately observed record strides of 92/76/52/68 bytes within polygon-processing routines.

This evidence advances the provenance chain:

```text
caller r20+92 / r20+140 / r22
    -> incoming a0 to cursor setup
    -> callee r16/r17 struct pointer
    -> +0 base and +12 cursor initialization
    -> +16 packet address computed from base + cursor entry
    -> GPU polygon packet and Ordering Table
```

## Confidence and missing information

The tool uses **bounded linear predecessor inspection** for each JAL; it does not perform full control-flow, liveness or alias analysis and does not interpret the MIPS delay slot as a pre-call argument source. The displayed instruction addresses and decoding were checked directly against the local EXE. The original runtime contents of `r20`, `r22`, the structure field `+0`, the cursor table, and GP0 opcode/UV/CLUT/TPAGE fields are **not recovered**. Next inspect where `r20` and `r22` are assigned inside the calling routine, then find their own data sources.

## Verification

```sh
python3 tools/audit_gp0_structure_callers.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

On the local original executable, the scanner reproduced all three table rows. Nine synthetic tests in `tests/test_gp0_structure_callers.py` check direct JAL matching, signed ADDIU values, ADDU copies, nearest definitions, unrelated register writes, excluded delay-slot definitions, invalid addresses and absent calls.

The full staged host CMake/C++20 build was run, and **41/41 CTest suites passed** (including `wa_original_gp0_structure_callers`). This is a host-side analysis milestone, not full PlayStation hardware validation or a playable Nintendo Switch build. GitHub Actions CI was not checked for this change.
