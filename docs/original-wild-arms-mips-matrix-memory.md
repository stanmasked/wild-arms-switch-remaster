# Stage 190 — private PS-X trig data and nine matrix output slots

The stage-187 linear MIPS interpreter can now access two **disjoint**
memory regions through `tools/mips_matrix_memory.py`:

- the original packed Q12 sin/cos table at `0x800CBE44`, marked
  **read-only**;
- a separate caller-selected, writable 18-byte matrix destination
  (`SH` offsets `0,2,4,6,8,10,12,14,16`).

The in-memory `prepare_from_private_exe(blob, matrix_address)` helper
validates a caller-owned PS-X EXE using the existing `parse_exe` code
and selects the 4096-entry table by virtual address. It never saves,
prints or commits original executable/table bytes. Memory-region overlap,
unaligned access and unmapped access are errors.

## Verified synthetic result

A **synthetic program**, not the original 0x800B7118 builder, executes
`LW; NOP; SRA; SLL; SRA` and nine `SH` operations. With the synthetic
cardinal table it writes this 3x3 Q12 identity matrix:

```
4096    0    0
   0 4096    0
   0    0 4096
```

A separate test verifies signed -4096, and synthetic PS-X EXE parsing
is exercised without any private game asset. Sixteen tests across
`test_mips_trig_memory.py` and `test_mips_matrix_memory.py` passed
on a local reconstruction of the relevant modules, including eight
new matrix-memory tests. The new tests are wired into CTest and
the matrix-audits GitHub Actions workflow.

## Limitations and next step

This is **not** execution of the original builder, and no claim of
bit-identical Wild Arms matrix output is made. The original code at
`0x800B7118–0x800B739C` can contain branches, external references,
GTE operations and hardware timing outside the current linear
interpreter. Its execution path and register inputs must be validated
against a user-provided private EXE before coefficient comparisons.

Local command:

```sh
python3 -m unittest discover -s tests -p test_mips_trig_memory.py -v
python3 -m unittest discover -s tests -p test_mips_matrix_memory.py -v
```

Full repository CI and hardware execution are not confirmed.
