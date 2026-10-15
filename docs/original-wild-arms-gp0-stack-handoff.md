# Original Wild Arms: stack polygon data handoff to renderer

## Evidence from the private original PlayStation executable

Used the user-owned, locally extracted `WILDARMS.EXE` loaded at `0x80011420`. Original copyrighted game bytes and assets stay local and are not published.

The caller around `0x800691D0` constructs one **caller-stack address** and passes it through two consecutive function calls:

| Address | MIPS instruction | Meaning |
|---|---|---|
| `0x800691D0` | `ADDIU r16,sp,32` | Pointer to caller stack +32 |
| `0x800691D4` | `ADDU a2,r16,zero` | Pass stack pointer as third argument |
| `0x800691D8` | `JAL 0x8007790C` | Preparation/helper call |
| `0x800691EC` | `JAL 0x80077D08` | Polygon processing call |
| `0x800691F0` | `ADDU a3,r16,zero` | Pass same address in JAL delay slot |

Inside `0x8007790C` the helper copies `a2` to its saved CPU register `r19` at `0x80077924`. It later copies `r19` to `a1` at `0x800779C0` immediately before `JAL 0x800B68E8` at `0x800779C8`.

This is new static evidence that the **same stack address** flows to a helper and then to the polygon renderer, and is forwarded again inside the helper to `0x800B68E8`. It does **not** recover actual data written into the region, prove the deeper callee writes it, or establish GP0/UV/CLUT/Texture Page values.

## Reproduce and validation

`tools/audit_gp0_stack_handoff.py` decodes nearby `ADDIU` stack offsets, register moves, direct JAL targets and the architectural JAL delay slot. It checks stack offsets for equality; different offsets are not conflated. The helper follow-up reports the `a2 -> r19 -> a1` chain and nested call target.

```sh
python3 tools/audit_gp0_stack_handoff.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

Verified with the privately held original EXE: one matched two-call handoff with stack offset **+32**, and helper nested target **0x800B68E8**. Ten synthetic tests pass, covering signed stack offsets, JAL decoding, correctly paired and mismatched stack objects, delay-slot register identity, empty input and the inner helper register chain.

**Complete local CMake/C++20 compilation and CTest: 44/44 passed.** The repository is a host-side geometry and reverse-engineering codebase, not a playable Nintendo Switch port. Hardware-exact GTE, runtime memory traces and GitHub Actions CI remain unverified.

## Next step

Inspect function `0x800B68E8` for direct/indirect stores through its incoming `a1` pointer, establish the stack structure fields and look for the first actual writes to GP0 command and texture data. Audit branch paths and aliases before claiming definite object initialization.
