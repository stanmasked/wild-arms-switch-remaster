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

## Stage 177 — predecessor-state recomputation

Context-sensitive source propagation now stores each node's OUT state
and recomputes a successor's IN state as a union of the **current** OUT
states of reachable predecessors. Previously it directly unioned new
information with the existing IN state, which could retain superseded
register sources in cyclic dataflow.

A synthetic loop regression writes a lookup source, overwrites the
register on every route to the matrix store, and loops back. The
reported candidate store must retain only the later lookup source.
This remains a possible-source abstraction and does not establish
exact arithmetic results or concrete branch predicates.

CI execution remains unverified; no original game executable bytes are
included in the repository.

## Stage 179 — GPR writes from coprocessor moves

The shared register-provenance transfer recognizes MFCn and CFCn
(COP0–COP3 with `rs=0` or `rs=2`) as GPR writes to `rt`.
Because this analysis does not model coprocessor register contents,
the previous GPR source set is killed. MTCn and CTCn (`rs=4/6`)
write into the coprocessor, leaving the source GPR unchanged.

Two synthetic test methods check the COP2 variants of both cases.
The model is still not a complete GTE interpreter and does not
derive numeric matrix coefficients. No game executable bytes are
committed and successful CI remains to be verified.
