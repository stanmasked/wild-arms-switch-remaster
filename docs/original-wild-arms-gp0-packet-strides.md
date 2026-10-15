# Original Wild Arms: GPU packet pointer and record strides

Audited the user's locally held, extracted original PlayStation `WILDARMS.EXE`, load address `0x80011420`. **No original executable, textures or game assets were uploaded.**

For each of the six previously established `NCLIP -> MAC0/BLEZ -> polygon packet -> OT` instruction paths, the CPU copies an incoming `a0` address to packet pointer `r11` through `ADDU r11,a0,r0` and immediately advances `a0` to the next record with `ADDI a0,a0,immediate`. The `r11` register is later used for writing SXY vertices and the OT packet tag.

| NCLIP | Pointer alias | Advance | GP0 layout candidate | Stride bytes | GP0 command words after tag |
|---|---|---|---|---:|---:|
| `0x80066E2C` | `0x80066E0C` | `0x80066E10` | GT3 | 92 | 9 |
| `0x80066F64` | `0x80066F44` | `0x80066F48` | GT3 | 92 | 9 |
| `0x800670D8` | `0x800670B8` | `0x800670BC` | FT3 | 76 | 7 |
| `0x800671F8` | `0x800671D4` | `0x800671D8` | FT3 | 76 | 7 |
| `0x800673B8` | `0x80067398` | `0x8006739C` | F3 | 52 | 4 |
| `0x8006749C` | `0x8006747C` | `0x80067480` | G3 | 68 | 6 |

All six observed strides satisfy `stride_bytes = 8 * GP0_command_words + 20`. This is a numerical regularity, **not a proven interpretation of the additional record fields**. The record is larger than the GP0 command payload, suggesting other stored information but not determining its meaning.

The static result confirms that these rendering routines **consume an incoming sequence of existing packet records**. It does not identify the caller that allocated or initialized them, prove the source of UV/CLUT/TPAGE values, or recover their GP0 opcode bytes. Those require a call-site/pointer provenance analysis.

## Repeatable verification

Run using the user's privately extracted EXE, which must remain outside the repository:

```sh
python3 tools/audit_gp0_packet_stride.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

Seven regression tests cover the packet-address alias, both MIPS `ADDI` and `ADDIU`, all six observed stride values, invalid pointers, negative/zero increments, lookback limits, and empty input. The original EXE was examined offline; a full CMake/C++20 local project build passed **37/37 CTest suites**. No runtime execution, hardware-accurate GTE, GitHub Actions result, or playable Switch build is implied.
