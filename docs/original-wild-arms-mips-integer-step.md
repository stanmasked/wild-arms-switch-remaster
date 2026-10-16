# Stage 185 — concrete MIPS integer stepper

`tools/mips_integer_step.py` operates on 32 general-purpose 32-bit
registers and HI/LO, executing **one** supported integer instruction
per call. It uses the stage-184 host-independent arithmetic helpers.

Supported instructions include shifts, MULT/MULTU, MFHI/MFLO, MTHI/MTLO,
ADD/ADDU, SUB/SUBU, AND/OR/XOR/NOR, SLT/SLTU, ADDI/ADDIU,
SLTI/SLTIU, ANDI/ORI/XORI and LUI. Register zero remains immutable,
and overflowing trapping arithmetic raises OverflowError.

Unsupported instructions raise ValueError. Branching, load delays,
memory accesses, exceptions, precise CPU timing and all GTE registers
remain outside this component. Accordingly this is **not** an emulator
or confirmed reconstruction of original game matrix values.

Synthetic verification:
```sh
python3 -m unittest discover -s tests -p test_mips_integer_step.py -v
ctest --test-dir build -R wa_mips_integer_step --output-on-failure
```
The test is also included in the matrix-audits workflow. CI success
and verification with the private original WILDARMS.EXE remain open.
No original game assets are committed.
