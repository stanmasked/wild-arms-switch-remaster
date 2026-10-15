# Original Wild Arms FT3/GT3 texture-field write audit

## Original game evidence

The user's privately held extracted `WILDARMS.EXE` was inspected locally at PS-X load address `0x80011420`. The scan builds on the six previously established `NCLIP → MAC0/BLEZ → SXY → GPU packet → OT` paths. **No game executable, models, textures or other proprietary game content is included in this repository.**

The GPU polygon-format *candidates* identified by packet length and position have the following texture words (byte offsets **from the start of the tag**, not from GP0 command data):

| Candidate | GP0 words after tag | UV0 + CLUT byte offset | UV1 + TPAGE byte offset | UV2 word byte offset |
|---|---:|---:|---:|---:|
| FT3 | 7 | +12 | +20 | +28 |
| GT3 | 9 | +12 | +24 | +36 |

In each packed word, two texture coordinates occupy the low 16 bits (U and V, one byte each). The word at UV0 contains the CLUT register in its high 16 bits; the word at UV1 contains the texture page in its high 16 bits; UV2's high 16 bits are not additional UV coordinates. Exact values and GPU opcodes have **not** been recovered from the original packet data.

## Real EXE audit result

`tools/audit_gp0_texture_fields.py` verifies direct MIPS writes via `SB`, `SH`, `SW` and `SWC2` to any byte overlapping those expected texture words, using the same CPU base register that addresses the polygon packet. It inspects the **linear fallthrough range starting after the BLEZ delay slot and ending at its forward target**.

| Original NCLIP site | Candidate | Direct writes to UV/CLUT/TPAGE words in this interval |
|---|---|---|
| `0x80066E2C` | GT3 | None |
| `0x80066F64` | GT3 | None |
| `0x800670D8` | FT3 | None |
| `0x800671F8` | FT3 | None |

**4 textured paths inspected; 0 direct field stores in those intervals.**

This proves only absence of **matching direct stores inside these bounded linear instruction ranges**, not that the original game never updates textures, not that their fields were necessarily initialized earlier, and not that other base registers or aliases cannot write the same memory. Source-buffer preparation or initialization remains to be investigated with control-flow and pointer provenance analysis.

## Reproduction and test verification

```sh
python3 tools/audit_gp0_texture_fields.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

Eight synthetic tests in `tests/test_gp0_texture_fields.py` check FT3/GT3 offsets, signed field offsets, byte/halfword/word overlap, non-packet pointers, color/SXY non-overlap, BLEZ delay-slot exclusion, invalid scan ranges and an empty image.

The full local host project configured and built successfully with CMake and GCC C++20; **36/36 CTest suites passed**, including the new `wa_original_gp0_texture_fields` suite. The report from the privately held original EXE was additionally executed locally. GitHub Actions and any playable Switch executable remain unverified. The experimental GTE reference is still not authenticated as fully PS1 hardware-exact.

Next step: locate how candidate FT3/GT3 packet memory is allocated and populated and trace actual GP0 opcode, UV, CLUT and TPAGE fields at creation time.
