# Wild Arms: rotation matrix load preceding polygon MVMVA

## Original game evidence

The privately held original PS-X `WILDARMS.EXE` was inspected locally (load address `0x80011420`). The original EXE and copyrighted game resources remain outside the repository.

In function `0x8007790C`, code calls `0x800B6DD8` at **`0x80077988`**, with MIPS JAL delay-slot instruction at `0x8007798C` setting `a0 = sp + 16`. This argument is a pointer to five packed rotation-matrix words. The helper `0x800B6DD8` loads five consecutive 32-bit words into CPU r8-r12, and uses `CTC2` to transfer them to GTE control registers 0-4.

| Local EXE LW address | Local EXE CTC2 address | Source offset | GTE control register |
|---|---|---:|---|
| `0x800B6DD8` | `0x800B6DEC` | +0 | 0: R11/R12 |
| `0x800B6DDC` | `0x800B6DF0` | +4 | 1: R13/R21 |
| `0x800B6DE0` | `0x800B6DF4` | +8 | 2: R22/R23 |
| `0x800B6DE4` | `0x800B6DF8` | +12 | 3: R31/R32 |
| `0x800B6DE8` | `0x800B6DFC` | +16 | 4: R33 |

Subsequently, at `0x800779C8`, the same outer function calls helper `0x800B68E8`, previously verified to execute `MVMVA` with rotation matrix and V0, then store IR1-IR3 through a pointer. The five GTE control words comprise the complete 3x3 rotation matrix in the PlayStation packed format (nine 16-bit coefficients). **The actual matrix coefficient values and any intervening matrix mutations at runtime have not been proven.** The call order is statically established, not a complete control-flow guarantee.

## Reproduction and scope

```sh
python3 tools/audit_gp0_rotation_matrix_load.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The original EXE scan reports `loader_called=true`, `delay_slot_a0_stack_offset=16`, `five_rotation_control_words=true` and `downstream_mvmva_helper_call=true`. Eleven synthetic regression tests verify load offsets, CTC2 targets, JAL delay slots, stack offsets, malformed callers and unknown matrix values.

The full locally staged CMake/C++20 project builds successfully, with **47/47 CTest suites passing**. No original game assets have been uploaded. This milestone does not establish PS1 hardware-exact fixed-point arithmetic, a complete original GP0 packet, or a playable Nintendo Switch application.

## Next investigation

Trace writes that fill the five words at caller stack offsets `sp+16` through `sp+32` before the rotation loader, including the routines called from `0x8007790C`. Then test how each packed matrix coefficient propagates through the existing GTE host reference.
