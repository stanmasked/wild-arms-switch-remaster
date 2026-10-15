# CDEF caller targets in WILDARMS.EXE — first-pass static opcode analysis

The user-owned original Wild Arms (USA) BIN image was read directly as CD-XA MODE2/Form1. Targets come from candidate `CDEF.BIN` JAL instructions and must not be mistaken for proven runtime calls.

| Target (main EXE) | Selected evidence from first instructions |
|---|---|
| `0x8007D564` | loads via `0x800D2E74`, checks byte at `a1 + 0x129`, branches on state, candidate JALs to `0x80079BF8`, `0x8007D1B8` |
| `0x800641E0` | `addiu sp,sp,-24`, calls `0x80063FFC` while placing zero in `a1` delay slot, restores stack and returns via `jr ra` |
| `0x80078DB0` | computes index from `a0`; loads pointer via `0x800D2C44`, writes bytes/halfwords and calls candidate `0x8006CE70` |

The `0x8007D564` routine's byte test at `a1 + 0x129` can be seen by `lw a?; lbu v1,1(v0)` after `lw v0,0x128(a1)` — these are chained loads, **not** a direct byte access at `a1+0x129`. This wording is corrected here: it reads a pointer/word at `a1+0x128`, then byte offset 1 from that loaded address.

**Limits:** window-based opcode scanning has no full CFG, register value analysis, or delay-slot execution simulation. These are static code signatures. Actual function role, reachability and CDEF runtime base are unconfirmed.

Reproduce with locally owned original disc:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.audit_cdef_callees 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_audit_cdef_callees.py' -v
```
