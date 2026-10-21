# Stage412 — shared transfer caller families and unresolved source-slot writes

The private, user-provided original `WILDARMS.EXE` (794,624 bytes) is
available in the local analysis environment. The public repository contains
only source-free tools, synthetic fixtures and the following **metadata**.

## Static evidence from the original PlayStation executable

The function at runtime address `0x8002356C` has **14 aligned JAL call
sites**. A *limited eight-instruction look-back*, looking for immediately
adjacent `lui reg,0x800D; lw reg,offset(reg)` pairs, finds four families:

| Nearby global memory slot | JAL call sites with matching nearby pair |
| --- | ---: |
| `0x800D2EA0` | 5 |
| `0x800D2EA4` | 2 |
| `0x800D2EB8` | 2 |
| `0x800D2EEC` | 3 |
| Call sites with no matching nearby pair | 2 |

The counts describe **proximity of a direct load**, not fully reconstructed
argument origin. MIPS delay slots, branches, register arithmetic, overwrites,
computed pointers and calls elsewhere may change the argument. In particular,
**this does not identify the source file or prove a CDFLR-specific loader**.

Across the declared executable text there are **nine** immediately adjacent
`lui/lw` reads of `0x800D2EA0`. The same narrow pattern finds **zero**
direct stores, and there are **zero** store opcodes with the exact 16-bit
offset `0x2EA0`, and **zero** aligned absolute u32 literals of that slot
address in the declared text. This is a useful negative result, but **does
not prove that no writer exists**: a store may use a computed base or the
whole memory region may be filled by another subsystem.

The callee itself contains a conditional-path `lhu v0,0(a0)` at runtime
address `0x800235F0` (EXE file offset `0x129D0`). This shows the passed
argument is **dereferenced as a pointer on at least that code path**; it
does not establish that path's reachability for the CDFLR candidate call,
nor that the value at the global slot is directly that pointer.

## Reproduction

```sh
python tools/audit_wild_arms_transfer_families.py \
  /private/path/WILDARMS.EXE > /private/path/transfer-families.json
python -m unittest discover -s tests -p 'test_audit_wild_arms_transfer_families.py'
```

Original asset bytes, opcode words, dialogue and sprites are **not printed
by the analyzer** and are not committed to GitHub. CI uses synthetic
fake PS-X EXE code with controlled load and store patterns.

## Next acceptance gates

1. Trace **computed/indirect writes** and call-specific reaching definitions
   of the value at `0x800D2EA0` using a bounded CFG or emulator watchpoint.
2. Identify which arguments are offsets or pointers after register arithmetic,
   rather than treating every nearby load as a complete data-flow proof.
3. Follow the callee's descriptor interpretation and data-fetch path to an
   actual ISO9660 file and LBA **before** naming a source container.
4. Keep the candidate palette/data pairs in CDFLR separate from confirmed
   graphics formats until actual PS1 reference output corroborates them.

All conclusions apply to the exact private USA disc candidate previously
checked by size and local SHA-256; they are not proof of other editions.
