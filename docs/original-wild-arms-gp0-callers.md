# Original Wild Arms: call sites and origins of GPU packet pointer a0

## Source and method

The audit uses the user's private, locally extracted original PS-X `WILDARMS.EXE` with load address `0x80011420`, and composes the prior six `NCLIP -> SXY -> OT` packet-path findings with direct MIPS `JAL` target reconstruction.

`tools/audit_gp0_callers.py` scans the complete EXE load image for `JAL` and associates **candidate nearby handler entry points** preceding known NCLIP sites. At each confirmed direct call, it inspects the nearest previous textual instruction defining CPU argument register `a0`, without pretending that a linear lookback is complete control-flow/dataflow analysis.

## Findings from original executable

| NCLIP site | Layout candidate | Direct handler target candidate | JAL instruction | Last a0 assignment |
|---|---|---|---|---|
| `0x80066E2C` | GT3 | `0x80066DC8` | `0x80076ADC` | `LW a0,16(r17)` at `0x80076AD4` |
| `0x80066F64` | GT3 | `0x80066EC8` | `0x80076B08` | `LW a0,16(r17)` at `0x80076B00` |
| `0x800670D8` | FT3 | Not directly resolved | None identified | Unknown |
| `0x800671F8` | FT3 | `0x80067158` | `0x8007707C` | `LW a0,16(r16)` at `0x8007706C` |
| `0x800673B8` | F3 | `0x80067354` | `0x80076D88` | `LW a0,16(r16)` at `0x80076D80` |
| `0x8006749C` | G3 | `0x80067438` | `0x80076B24` | `LW a0,16(r17)` at `0x80076B1C` |

**Five of six paths have direct JAL candidates, and all five load a0 from structure field +16**, through CPU registers r16 or r17. This is a useful next provenance anchor: subsequent work should identify the creation/population and lifetime of the structures whose +16 field holds the pointer, along with the target memory itself.

The unresolved first FT3 path could be reached through another branch or indirect control flow; its lack of a matching direct JAL must not be interpreted as dead code. The nearest JAL target selection, and nearest pre-call a0 assignment, are *static heuristics*: further control-flow tracking is required to validate every path and the runtime value of the pointer.

## Verification

With an extracted user-owned local EXE:

```sh
python3 tools/audit_gp0_callers.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

Offline original-EXE output: 6 packet paths, 5 with direct JAL caller candidates, all 5 with nearest `LW a0,+16(base)` evidence.

Nine additional synthetic Python tests in `tests/test_gp0_callers.py` validate JAL address construction, high-address region handling, signed LW offsets, negative ADDIU immediates, ignoring writes to non-a0 registers, explicit ADDU sources, repeated callers, nearest textual a0 definitions, and empty-image behavior.

**A fresh local CMake/C++20 build passed 38/38 CTest suites** including `wa_original_gp0_callers`. No GitHub Actions result or Nintendo Switch executable is implied.

No original game executable, models, textures or other copyrighted Wild Arms game content were committed. Original GPU opcode bytes, UV, CLUT and TPAGE values remain unknown; this report supports follow-up pointer provenance, not their recovery.
