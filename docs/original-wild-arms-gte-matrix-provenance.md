# Stage 162: conservative lookup-to-matrix provenance

The original Wild Arms rotation builder uses six indexed sine/cosine word
loads and stores nine halfword coefficients into the GTE rotation matrix.

`tools/audit_gp0_matrix_provenance.py` adds **conservative, straight-line**
register provenance. At each known lookup instruction, a symbolic source
marker is attached to the LW destination register. Recognized moves through
integer arithmetic, shifts, MULT/MULTU -> HI/LO -> MFHI/MFLO are propagated
within a basic block. A subsequent SH into a1 offsets 0..16 reports
candidate source addresses (not table values).

All taken and not-taken control-flow paths remain unresolved. On encountering
a branch or jump, analysis processes the delay slot, then clears register
provenance rather than speculatively following either successor.

Run locally with the user-owned extracted executable:

```sh
python3 tools/audit_gp0_matrix_provenance.py /private/path/WILDARMS.EXE
python3 -m unittest discover -s tests -p test_gp0_matrix_provenance.py
ctest --test-dir build -R wa_original_gp0_matrix_provenance --output-on-failure
```

## Scope and remaining limitations

- Only known lookup PCs are designated as sources; no game data samples,
  binary words, or original table contents are published.
- This is not an inter-block dataflow analysis and is not a path-sensitive
  interpreter. Store output is a *candidate relationship*, never a proof of
  runtime reachability.
- Unhandled opcode definitions and memory aliasing can interrupt provenance,
  and branch-delay-slot corner cases need stronger control-flow validation.
- Final Q12 sign extension, multiplication overflow and rounding behavior
  must be established separately against the original binary.
- The synthetic tests and CMake registration are added; complete native CI
  and execution with the private original EXE have not been verified here.

Next step: construct a minimal control-flow graph with branch targets,
propagate conservative provenance across predecessor joins, and independently
validate all nine coefficient stores.
