# Stage 171 — context-sensitive register provenance

This stage introduces `tools/audit_gp0_matrix_context_sources.py`, integrating
the stage-170 context-labelled MIPS CFG with the stage-165 symbolic GPR/HI/LO
transfer function. Worklist propagation operates on full context node labels,
so an address reached normally is not conflated with the same address executed
as a delay slot of another branch. At join points, candidate lookup sources
are unioned, not interpreted as definite values.

Use with a privately extracted original executable:

```sh
python3 tools/audit_gp0_matrix_context_sources.py /private/path/WILDARMS.EXE
python3 -m unittest discover -s tests -p test_gp0_matrix_context_sources.py
ctest --test-dir build -R wa_original_gp0_matrix_context_sources --output-on-failure
```

Synthetic regression cases cover HI/LO across a conditional branch,
a branch re-entering its own delay-slot address normally, unsupported
external calls, and invalid ranges. No original copyrighted game bytes
are embedded or emitted.

**Not yet proven:** branch predicates, precise MIPS integer values, GTE
matrix coefficients, behavior of unsupported instructions, or complete
runtime reachability. The CFG model is intentionally incomplete. The
changes are committed and registered in CTest, but successful CI execution
and testing against the private original EXE remain unconfirmed.
