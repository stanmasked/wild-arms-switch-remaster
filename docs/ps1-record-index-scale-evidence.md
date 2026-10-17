# Stage 232 — bounded static MIPS record-index coefficient evidence

The older record verifier inferred a **364-byte record stride** from eight
committed MIPS arithmetic instructions. Independent decoding showed that the
actual checked-in prefix computes `677 × index`, and the third `GLOBAL_WORDS`
instruction shifts that result left twice, giving **2708 × index** (modulo
32-bit arithmetic).

This is an observed property of the **checked-in opcode signature**, not yet
proof of the original Wild Arms game structure or its element size. The 364
figure remains unsupported for these exact bytes, and the normal
`inspect_exe` report must still **reject** the contradiction. The separate
88-byte indexed initializer signature in
`tools/verify_indexed_init_call.py` concerns a **different code site and
structure**; its coefficient must not be substituted for either candidate.

## Evidence method

The new `_static_index_scale` evaluates just the exact recognized
MIPS `SLL` and `ADDU` words, checking actual source/destination fields
and preserving 32-bit register semantics. It models incoming `a1` as
coefficient 1, not a real address or debugger register snapshot. It then
consumes only the final `SLL v0,v0,2` of `GLOBAL_WORDS`, skipping the
unrelated memory-address-loading instructions.

Synthetic sequence:

| Operation | Index coefficient |
| --- | ---: |
| `sll v0,a1,2` | 4 |
| `addu v0,v0,a1` | 5 |
| `sll v0,v0,2` | 20 |
| `addu v0,v0,a1` | 21 |
| `sll v0,v0,3` | 168 |
| `addu v0,v0,a1` | 169 |
| `sll v0,v0,2` | 676 |
| `addu v0,v0,a1` | 677 |
| `sll v0,v0,2` (final global prefix word) | **2708** |

The old alternative computation
`stride_from_index_words(INDEX_WORDS)` is retained as a second oracle;
the tests require both independent calculations to agree.

## Optional read-only private disc check

With an authentic **user-owned** raw MODE2/Form1 image and inventory file,
run locally:

```sh
python3 -m tools.verify_record_stride /private/WildArms.bin \
  /private/disc-inventory.json --index-evidence-only
```

The tool validates three target function signatures against the same exact
eleven opcode words and returns only the count of matching sites, static
index coefficient, and conservative flags. It does **not** emit original
instruction bytes, raw game files, addresses, register values, memory,
offset tables or copyrighted assets. Never upload the disc image or a
private capture to GitHub.

A matching signature would strengthen evidence that those three
locations in *that* EXE use the 2708 index multiplier, but still would
**not** authenticate original PS1 execution, describe pointer use after
the prefix, or establish actual record boundaries. A divergent target,
truncated EXE, or modified opcode fails closed with a generic error
and no partial numeric output. The existing normal verifier's refusal
to certify a 364-byte stride remains intentional.

## Verification and next step

Synthetic unit tests cover all three matching sites, independent
opcode interpretation, mutated shifts, isolated mismatches, bounded
EXE input, privacy fields, and unchanged refusal of false stride
certification. CI confirms host regressions only; a genuine disc
comparison and runtime debugger trace must be performed privately
before reporting the game's true record layout. No Nintendo Switch
binary or original-game asset is created by this change.
