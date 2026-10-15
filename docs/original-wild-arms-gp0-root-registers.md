# Original Wild Arms: root origins of polygon structure registers

The local, privately extracted original `WILDARMS.EXE` was examined at PlayStation load base `0x80011420`. Original code bytes, textures, models, the BIN and resource content **remain local and are not committed**.

The previous caller audit found two polygon cursor-setup structures addressed via `r20+92` and `r20+140`, and a third via a copy of `r22`. The next reverse trace identifies these register sources:

| Function / site | Instruction evidence | Register value origin |
|---|---|---|
| `0x80077D08` main polygon loop, `0x80077D1C` LUI / `0x80077D20` LW | `LUI r20,0x800D`; `LW r20,0x2C3C(r20)` | 32-bit global pointer at **0x800D2C3C** |
| `0x80077D08`, `0x80077D30` | `ADDU r22,a3,r0` | Incoming fourth MIPS argument **a3 (r7)** |
| `0x80078280` second polygon routine, `0x80078288` LUI / `0x8007828C` LW | `LUI r22,0x800D`; `LW r22,0x2DB8(r22)` | 32-bit global pointer at **0x800D2DB8** |

Therefore, in the main polygon loop, `r20+92` and `r20+140` are offsets into a structure pointed to by the global 0x800D2C3C. A separately handled path receives a structure pointer through a3. A different routine uses the global pointer at 0x800D2DB8 as its own r22 base; this should not be conflated with the main loop's a3-derived r22.

**These addresses identify memory locations containing pointers, not the pointer values themselves.** Their runtime contents, object lifetime and packet/UV/CLUT/TPAGE bytes remain unknown.

`tools/audit_gp0_root_registers.py` performs conservative LUI+LW and ADDU source checks on these specific instructions; it outputs address evidence only. It does not do whole-program pointer alias analysis or prove execution of any branch. The eight regression tests check the global-address calculation (including signed LW offsets), copying a3, destination mismatches, unresolved sources, invalid addresses and empty input.

## Verified locally

```sh
python3 tools/audit_gp0_root_registers.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The scanner produced all three expected source entries from the original local EXE. Full CMake/GCC host build and **42/42 CTest suites passed**, including `wa_original_gp0_root_registers`. This remains an offline analysis result, not a runtime data capture, PS1 hardware-accurate renderer, successful CI verification, or playable Switch game.

Next inspect who writes the globals `0x800D2C3C` and `0x800D2DB8`, then trace the incoming a3 argument at callers of `0x80077D08` to find allocation and initialization of the polygon structure.
