# Original Wild Arms: construction of polygon packet pointer at structure +16

## Source and method

Inspected the user's **locally held** extracted `WILDARMS.EXE`, with PS-X load address `0x80011420`. No original binary, models, textures or game assets were uploaded. An independent static opcode scanner, `tools/audit_gp0_packet_field16.py`, locates MIPS pointer arithmetic writing field `+16` of polygon-control structures using registers r16 or r17.

The narrow scanner recognizes an `LW` from structure offset `+0`, a second `LW` from `[cursor+0]` or `[cursor+4]` where cursor was loaded from structure offset `+12`, an `ADDU` combining those words, and an `SW` into structure offset `+16`. This is **bounded textual instruction-pattern evidence**, not a full, path-sensitive MIPS register/alias analysis.

## Confirmed original-EXE matches

| Store computed pointer | Structure CPU register | Cursor's word offset | Cursor load | Offset value load | Base value load | ADDU |
|---|---|---:|---|---|---|---|
| `0x80076A84` | r17 | +0 | `0x80076A64` | `0x80076A6C` | `0x80076A78` | `0x80076A80` |
| `0x80076D28` | r16 | +0 | `0x80076D14` | `0x80076D1C` | `0x80076D18` | `0x80076D24` |
| `0x80076FDC` | r16 | +4 | `0x80076FAC` | `0x80076FCC` | `0x80076FC8` | `0x80076FD8` |

The observed computation is approximately:

```text
record.pointer_at_16 = record.base_at_0 + *(record.cursor_at_12 + (0 or 4))
```

The three sites are near the processing loops that issue the previously established five direct polygon-renderer JAL calls, whose `a0` arguments load `+16` from structures in r16/r17. The scanner reports **5 call-site contexts** using the same field/reg classes. This is a plausible pointer-provenance connection, **not proof that an individual store reaches a particular call**, nor proof of the underlying offset table's encoding, memory allocations, or runtime pointer contents.

## Verification

The real offline local scan found **3 pattern matches**, with cursor word offsets 0, 0, 4. Nine synthetic parser tests cover both structure base registers, both cursor layouts, incorrect destination fields, cursor fields, wrong address registers/offsets, `ADD` versus `ADDU`, and empty input.

The full staged CMake C++20 project was configured and compiled, and **39/39 CTest suites passed** (including `wa_original_gp0_packet_field16`). This verification is offline static analysis; GTE hardware fidelity, GPU drawing, GitHub Actions and Nintendo Switch execution remain unverified.

To reproduce on a locally extracted game file:

```sh
python3 tools/audit_gp0_packet_field16.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

## Next step

Trace where structure offset `+0` and cursor `+12` are assigned, and whether offsets from the cursor refer to polygon packet templates or object data. Then inspect actual runtime contents or verifiable initialization writes to resolve the initial GP0 opcode, UV, CLUT and Texture Page. Neither field contents nor initial template data have been recovered at this stage.
