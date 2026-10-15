# Original Wild Arms GTE rotation builder: integer arithmetic audit

Stage 161 introduces `tools/audit_gp0_matrix_arithmetic.py` to statically list
MIPS I arithmetic instructions within `0x800B7118..0x800B739C`
(inclusive) using a user-supplied, privately extracted `WILDARMS.EXE`.

Supported opcode forms: `MULT`, `MULTU`, `MFLO`, `MFHI`,
`SLL`, `SRL`, `SRA`, `SLLV`, `SRLV`, `SRAV`.
Reserved fields are checked for selected opcodes, and the zero-word NOP
is not counted as a substantive shift.

Usage:

```sh
python3 tools/audit_gp0_matrix_arithmetic.py /private/path/WILDARMS.EXE
python3 -m unittest discover -s tests -p test_gp0_matrix_arithmetic.py
ctest --test-dir build -R wa_original_gp0_matrix_arithmetic --output-on-failure
```

The report lists addresses, operation names, register indices and immediate
shift amounts. It **does not** include original instruction words, executable
bytes or trig-table samples. The tests use entirely synthetic instructions.

This decoder is a **static inventory**, not a data-flow reconstruction.
Its results do not prove which sine/cosine halfword reaches which output
matrix slot, which branches execute, or whether signed intermediate
overflow matches the original PS1 CPU. The private EXE must be audited
locally; repository CI can only check the opcode-decoder contract.

Next: trace register definitions and uses from each of the six indexed
lookups to the nine `SH` coefficient destinations, preserving
sign extension, HI/LO arithmetic, shift amounts and branch-delay slots.
