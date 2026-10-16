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

## Stage 176: annulled-slot source propagation tests

Two additional synthetic provenance regressions cover branch-likely and
REGIMM-likely control flow. Both test a lookup load in the delay slot,
where only the taken path executes the load; the not-taken path annuls
it. The merge at the destination must retain the lookup as a **possible**
source, never assert that it is certain.

These tests protect the integration between the stage-175 CFG and the
context-sensitive symbolic register dataflow. They do not infer branch
predicates or recover concrete GTE matrix values. The private original
WILDARMS.EXE is not stored in the repository.
