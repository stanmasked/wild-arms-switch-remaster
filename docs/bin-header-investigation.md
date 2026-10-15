# BIN container header investigation — first pass

Examined first 2048 logical payload bytes from raw MODE2/Form1 sectors
of the user-owned Wild Arms (USA) disc image.

Several BIN files begin with aligned 32-bit little-endian values in the
PS1 KSEG0 memory range `0x80000000..0x801fffff`:

| File | First 32-bit values (hex) |
|---|---|
| CDSTG.BIN | 8015f624, 00000000, 8014f040, 00010800 |
| CDFLR.BIN | 80183100, 8018e62c, 8019d790, 8019d968 |
| CDEN.BIN | 801d0100, 801d01f8, 801d03f8, 00000000 |
| CDEF.BIN | 8017ee04, 8017ee7c, 8017ef30, 8017eff4 |
| CDGD.BIN | 8017c088, 8017c0fc, 8017c160, 8017c1e4 |
| CDPL00.BIN | 801a3100, 801aa870, 801aae50, 801ace20 |

`CDGD.BIN` also contains words resembling MIPS R3000 instructions
near byte offset 0x1c (e.g. `27bdffa0`, `afb20050`).

**Interpretation:** These are strong candidates for in-memory pointer
tables and loadable code/data overlays rather than ordinary self-describing
file archives. The mapping from pointers to file offsets is **not proven**.
No asset boundary, compression scheme or file index has been verified yet.

Run locally:
```sh
python3 tools/inspect_disc.py "Wild Arms (USA).bin" --json > disc-inventory.json
python3 tools/probe_bin_pointers.py "Wild Arms (USA).bin" disc-inventory.json
```
No copyrighted data is included in this repository.
