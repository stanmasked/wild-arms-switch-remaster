# Original Wild Arms polygon data cursor lifecycle

## Original game and scope

Using the locally extracted original Wild Arms PS-X EXE (load address `0x80011420`), audited the origin and movement of field `+12` in polygon-control structures accessed through CPU registers r16 and r17. The game EXE and its assets remain private and are **not uploaded or committed**.

The previously confirmed renderer sequence calculates the packet pointer at structure `+16` using a base pointer from `+0` and a 32-bit word fetched through the cursor at `+12`. This audit looks one step earlier.

## Confirmed MIPS instruction patterns

The new `tools/audit_gp0_cursor_lifecycle.py` recognizes two narrow patterns using `LW`, `ADDI/ADDIU` and `SW`:

1. **Cursor initialization:** `LW tmp,0(struct)`, `ADDIU cursor,tmp,12`, `SW cursor,12(struct)`.
2. **Cursor advancement:** `LW cursor,12(struct)`, `ADDIU cursor,cursor,4`, `SW cursor,12(struct)`.

The original EXE yielded **3 initializations and 9 four-byte advances** inside the audited render-handling routines, scanning `0x80076900` through `0x80077100`.

| Cursor setup SW | Structure register | Source `LW +0` | `+12` computation |
|---|---|---|---|
| `0x80076950` | r17 | `0x80076940` | `0x8007694C` |
| `0x80076BD0` | r16 | `0x80076BC0` | `0x80076BCC` |
| `0x80076F78` | r16 | `0x80076F6C` | `0x80076F74` |

The nine `+4` cursor-update stores occur at `0x80076984`, `0x80076A60`, `0x80076A74`, `0x80076C08`, `0x80076CFC`, `0x80076D38`, `0x80076F9C`, `0x80076FB8` and `0x80076FD4`.

**Interpretation:** these paths initialize the cursor to the beginning of a region 12 bytes after the object's base and traverse its 32-bit entries. Other code also changes the cursor via branches or larger offsets; these two patterns are not a complete control-flow model or a verified data structure definition. Some loads combine offsets with `+0` to produce the GPU packet pointer stored at `+16`, but the *actual contents* of the table, its allocation and the GP0 texture fields are unknown.

## Reproduce and verify

```sh
python3 tools/audit_gp0_cursor_lifecycle.py /private/path/WILDARMS.EXE --region-start 0x80076900 --region-stop 0x80077100
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

Ten synthetic unit tests verify decoding, both register bases, initialization and advancement, ADDI support, wrong field/register/offset rejection, scan range boundaries and truncated input. The full staged local C++20 host build completed and **40/40 CTest suites passed**. The scan of the original locally held EXE independently reproduced **3 setup and 9 advancement matches**.

## Limitations and next investigation

This is a bounded linear MIPS opcode pattern analysis, not runtime tracing or verified pointer aliasing. It neither recovers original GP0 opcode bytes nor UV, CLUT, TPAGE contents. Next trace the structure's field `+0` pointer provenance and the memory region beginning at `base+12`, then inspect template initialization. Hardware GTE correctness, GitHub Actions CI and Nintendo Switch native game execution have not been established.
