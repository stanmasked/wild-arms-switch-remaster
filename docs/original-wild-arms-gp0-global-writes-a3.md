# Wild Arms polygon roots: global write search and a3 delay-slot provenance

## Original executable evidence

Inspected the user-provided, privately held PS-X `WILDARMS.EXE`, loaded at `0x80011420`. The original binary, graphics and all proprietary game assets remain outside GitHub.

The earlier reverse-engineering path found the polygon root pointers loaded via global slots **0x800D2C3C** and **0x800D2DB8**, and a third root received as the incoming fourth MIPS argument `a3` in the main processing function `0x80077D08`.

The new `tools/audit_gp0_global_writes_a3.py` makes two independent checks:

1. Scan the complete original EXE load image for a **direct `SW source,offset(base)`** targeting either global slot with an upstream `LUI base,high16` in the preceding 12 instructions. On the original EXE this narrow pattern returns **zero candidates** for either global slot. This does **not** prove either location is read-only, nor rule out register aliases, indirect stores, or initialization outside the scanned EXE.
2. Find direct `JAL 0x80077D08` and **decode its actual MIPS branch delay-slot instruction**, which executes before control reaches the callee. This reveals the source of `a3`:

| Instruction | Address | Interpretation |
|---|---|---|
| `ADDIU r16,sp,32` | `0x800691D0` | Prepare a pointer to the caller's stack area |
| `JAL 0x80077D08` | `0x800691EC` | Call polygon-handling routine |
| `ADDU a3,r16,zero` | `0x800691F0` | Pass that stack area as fourth argument **in the JAL delay slot** |

This independently explains the main loop's earlier `ADDU r22,a3,zero`: its r22 structure base comes from an area starting at the caller's `sp+32`, rather than directly from a global-slot load. **The stack region's actual fields and game runtime pointer values remain unknown.** Reading memory or a more complete control-flow trace would be needed to establish its layout and how its contents are populated.

## Tests and reproducibility

Run the scanner on a **locally extracted** user-owned game executable:

```sh
python3 tools/audit_gp0_global_writes_a3.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The original EXE scan found no direct global stores in this pattern and one direct `JAL` with `a3=r16=sp+32`. Ten synthetic tests cover both global addresses, signed-offset addressing, rejecting wrong-base and `LW`, delay-slot sources, nonmatching calls and unknown provenance.

The complete locally staged host project configured and built under CMake/C++20; **43/43 CTest suites passed**. The results are evidence of this narrow static analysis, not PS1 hardware-accurate GTE, a completed Nintendo Switch port or GitHub Actions CI status.

## Next investigation

Inspect stores to the caller's stack region at `sp+32` before `0x800691EC` and follow the initialization of the two global pointers through alias-aware dataflow or loading routines. Do not infer GP0 opcode/UV/CLUT/TPAGE values until actual packet data or writes are traced.
