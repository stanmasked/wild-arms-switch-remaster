# Original Wild Arms: GTE MVMVA helper populates intermediate polygon stack data

## Verified original executable instructions

The user-owned original PlayStation EXE was inspected **locally only**. No game executable, texture, model or disc content was committed. Prior static analysis identified `a2=sp+32` passed to `0x8007790C`; that routine forwards the pointer as `a1` to `0x800B68E8`. The new audit inspects the actual body of this second helper.

| Address | Instruction/function | Meaning |
|---|---|---|
| `0x800B68E8` | `LW r8,0(a0)` | Input word 0 |
| `0x800B68EC` | `LW r9,4(a0)` | Input word 1 |
| `0x800B68F0` | `MTC2 r8,VXY0` | Set GTE vector packed X/Y |
| `0x800B68F4` | `MTC2 r9,VZ0` | Set GTE vector Z register |
| `0x800B68FC` | `GTE MVMVA` (function 0x12) | GTE matrix/vector calculation |
| `0x800B6900` | `SWC2 IR1,0(a1)` | Write intermediate result 1 |
| `0x800B6904` | `SWC2 IR2,4(a1)` | Write intermediate result 2 |
| `0x800B6908` | `SWC2 IR3,8(a1)` | Write intermediate result 3 |

The first twelve bytes of the output structure are thus **three 32-bit stores of GTE result registers IR1, IR2 and IR3**. These are intermediate geometric components, not known original GP0 opcode/UV/CLUT/TPAGE fields. The `MVMVA` instruction's full control bits (matrix/vector selection, scale and shifts) need separate inspection before asserting an exact transformation.

This is a concrete follow-up to the stack-handoff result: data is being computed and written through the forwarded pointer, rather than only passing an uninitialized address.

## Reproduce

```sh
python3 tools/audit_gp0_helper_mvmva.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The audit matches the nine expected instruction slots (including the intervening NOP) exactly and rejects mutated commands, inputs, COP2 destination registers and output bases. Ten new unit tests in `tests/test_gp0_helper_mvmva.py` pass. The full local CMake/C++20 build passes **45/45 CTest suites**. The original EXE scan returned `matched: true`; that static evidence does **not** imply emulated PS1 runtime execution, hardware-accurate GTE arithmetic or a playable Nintendo Switch build.

## Next investigation

Trace the first `a0` input word pair passed to the helper, determine the MVMVA command control bits and downstream consumers of the three IR output words. Verify any claim about texture-packet initialization separately; original GP0 opcode, UV, CLUT and TPAGE values are **not** recovered here.
