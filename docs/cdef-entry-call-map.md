# CDEF repeated overlay entry-point J/JAL audit

Read-only analysis on the user-supplied *Wild Arms (USA)* MODE2/Form1 disc image; no copyrighted binary data uploaded.

Source regions `0x38000` and `0x3C000` were independently scanned over 0x60 bytes at each of two candidate entry points, under the **unverified** overlay base assumption `0x8017C000`.

| Entry point | MIPS op file-relative region offset | Instruction | Computed target | Static range |
|---|---:|---|---|---|
| `0x8017C7F8` | `0x80C` | JAL | `0x8007D564` | main EXE range |
| `0x8017C7F8` | `0x83C` | JAL | `0x800641E0` | main EXE range |
| `0x8017C7F8` | `0x844` | J | `0x8017CC40` | candidate overlay |
| `0x8017C84C` | `0x880` | JAL | `0x80078DB0` | main EXE range |

Both candidate region copies produce **identical jump instruction inventories**.
MIPS J/JAL addressing uses the high nibble of PC+4 and a shifted 26-bit field. File-relative offsets in the table are offsets **within each 16 KiB region**, not offsets in CDEF.BIN itself.

This is a *linear instruction-pattern scan*, not a complete disassembler or reachable CFG. No runtime trace proves these addresses are executed; three in-range EXE targets are not yet identified function entry points.

Five synthetic unit tests passed locally. Reproduce:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.audit_cdef_calls 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_audit_cdef_calls.py' -v
```

Next steps: trace candidate EXE targets, verify delay slots, and establish the overlay loader/base dynamically.
