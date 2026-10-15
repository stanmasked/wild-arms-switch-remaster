# WILDARMS.EXE: three CDGD call target signatures

Read-only static analysis of the user-owned Wild Arms (USA) image. Analyzed 0x50 bytes from each main-EXE target, using the load address from the PS-X EXE header (0x80011420).

| Virtual target | ISO file offset | First observed JR RA | Shared index prefix |
|---|---|---|---|
| 0x8006D258 | 0x5C638 | 0x8006D288 | yes |
| 0x8006DCA0 | 0x5D080 | 0x8006DCE4 | yes |
| 0x8006DCEC | 0x5D0CC | 0x8006DD38 | yes |

All three targets start with `00051080 00451021` (MIPS `sll v0,a1,2; addu v0,v0,a1`) and continue with analogous indexing operations. A global pointer is loaded using `lui v1,0x800d` plus `lw v1,0x2c3c(v1)`. The first two procedures contain memory stores within the observed 0x50-byte window; the third contains a branch and indirect flag update near its return.

**Interpretation:** likely repeated indexing into a shared structure, with state mutation. The index stride, structure identity, and gameplay significance are **not established**. A scanned `JR RA` is not proof of a reachable function boundary or safe pseudocode reconstruction. MIPS delay slots must be considered in further analysis.

Reproduce locally:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/audit_exe_functions.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

No game code or proprietary assets are committed.
