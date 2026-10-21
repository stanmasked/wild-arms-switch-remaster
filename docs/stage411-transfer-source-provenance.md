# Stage411 — provenance of the CD transfer call's first argument

This stage addresses an inference gap in Stage410: code that constructs a
destination buffer address `0x80183000` and copies `0x3A000` bytes is NOT
proof that a specific disc container (such as `CDFLR.BIN`) is the source.

## Source and status

A private, user-supplied `WILD ARMS.zip` was validated and extracted locally
in the analysis environment. The original `WILDARMS.EXE` is a 794,624-byte
PS-X EXE with a declared load address `0x80011420` and text length
`0xC1800`. Only metadata and source-free synthetic tests are committed.

## New observations from the original executable

- The function at PS1 runtime address `0x8002356C` is called by `jal`
  instructions from **14 distinct sites** in the executable. They are not
  all calls for the same buffer or byte count. This makes the subroutine
  a **shared transfer helper candidate**, not a dedicated CDFLR loader.
- One of those 14 calls, at **file offset `0x58B00`**, constructs arguments
  `a1 = 0x80183000` (destination) and `a2 = 0x3A000` (byte count).
- That call's `a0` argument is obtained by a `lui a0,0x800D` /
  `lw a0,0x2EA0(a0)` pair: it reads a **runtime value** stored at
  `0x800D2EA0`; it is NOT an inline constant identifying `CDFLR.BIN`.
- The candidate source-pointer slot address `0x800D2EA0` is **640 bytes
  beyond the executable's declared text end** `0x800D2C20`.
  The original PS-X EXE has **zeroed BSS address/length fields**, so
  this observation alone does NOT prove the slot is BSS.
- A narrow, immediately-adjacent `lui/lw` scan finds **9 direct reads** of
  that same runtime slot in the original executable. This is not a complete
  dataflow or memory-write analysis; indirect accesses may exist.

The first argument's runtime value could depend on earlier file selection,
scene state, or other game activity. Therefore a stronger conclusion such
as "this exact call reads CDFLR.BIN" would be premature.

## Synthetic-only verification

```sh
python -m unittest tests/test_audit_wild_arms_transfer_calls.py
python tools/audit_wild_arms_transfer_calls.py /private/path/WILDARMS.EXE \
  > /private/path/wild-arms-transfer-calls.json
```

The analyzer validates PS-X EXE bounds and recognizes the seven-instruction
call argument window, including the MIPS branch delay slot. It enumerates
aligned `jal` calls to the shared subroutine, reports only metadata and
file offsets, and fails closed on invalid headers/declared text. It neither
executes MIPS nor prints protected code bytes.

## Next acceptance gate

1. Identify **writers** to the runtime source-pointer slot, including
   indirect and computed-address stores. This requires bounded control/data
   flow or a reference-emulator memory trace, not a naïve byte search.
2. Cross-reference the slot value with ISO9660 extent/LBA selections and
   confirm which file is chosen during actual gameplay.
3. Keep the candidate palette-size spans in `CDFLR.BIN` *separate* from
   image-decoder claims until a real frame/CLUT combination is verified.

No original BIN, CUE, EXE, raw bytes, graphics or text are committed.
