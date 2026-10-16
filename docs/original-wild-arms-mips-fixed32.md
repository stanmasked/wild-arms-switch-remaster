# Stage 184 — pure MIPS 32-bit integer reference

`tools/mips_fixed32.py` provides host-independent integer primitives for
later comparison with the original PlayStation rotation-matrix arithmetic:
32-bit unsigned wrapping, signed interpretation, 16-bit immediate sign
extension, signed/unsigned multiplication into 32-bit HI/LO halves,
SLL/SRL/SRA, signed addition/subtraction with overflow reporting,
ADDIU-style non-trapping addition and SLT/SLTU.

The arithmetic is deliberately separated from the symbolic graph.
It does **not** yet execute original MIPS instructions or account for
pipeline delays, exception delivery, memory access or GTE saturation.

Synthetic host regression:
```sh
python3 -m unittest discover -s tests -p test_mips_fixed32.py -v
ctest --test-dir build -R wa_mips_fixed32 --output-on-failure
```
The same test is registered in the GitHub Actions matrix audit workflow.
Code and tests are committed; successful CI or results against the private
WILDARMS.EXE have not been confirmed. No original game assets are included.
