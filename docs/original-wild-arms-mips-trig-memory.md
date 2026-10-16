# Stage 188 — mapping the packed Q12 trigonometric table

`tools/mips_trig_memory.py` maps exactly 4096 caller-provided
little-endian 32-bit packed words to a bounded guest memory region.
Each word encodes a signed 16-bit sine in its low half and a signed
16-bit cosine in its high half. Indexing masks the input angle to
12 bits; addresses are base + 4 * index. These conventions originate
from prior static analysis of the user's original Wild Arms executable.

The module provides a sparse **synthetic** cardinal-angle fixture,
not an extracted or distributable original table. Six tests exercise
signed quadrant decoding, index wrap, memory size, alignment and a
linear `LW; NOP; MULT; MFLO; SRA` calculation that respects the
one-instruction load-delay rule.

Verification command:

```sh
python3 -m unittest discover -s tests -p test_mips_trig_memory.py -v
```

The test has been registered for CTest and matrix-audits GitHub
Actions. **Execution of these tests and full CI success are not yet
verified.** The reconstructed program covers only a synthetic
linear instruction chain, not the original matrix builder or GTE.
Original game executable and texture/audio assets are not committed.
