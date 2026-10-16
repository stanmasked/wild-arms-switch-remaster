# Stage 170 — context-sensitive delay-slot CFG prototype

The new `tools/audit_gp0_matrix_context_cfg.py` explores a restricted
control-flow graph using nodes `(instruction_pc, controlling_branch_pc)`.
The second component is empty during ordinary entry and populated when
executing the delay slot of a supported conditional branch or direct jump.
This distinction prevents an address entered normally from being conflated
with that same address executing as another instruction's delay slot.

Supported: sequential execution, direct J, BEQ/BNE/BLEZ/BGTZ and
non-linking BLTZ/BGEZ. Conditional outcomes are both explored.
Unsupported: JAL, JR/JALR, branch-likely, REGIMM link branches, control
transfers inside delay slots, and external targets. Such cases are reported
as unresolved and traversal stops at that edge.

Run using the user-owned original executable:

```sh
python3 tools/audit_gp0_matrix_context_cfg.py /private/path/WILDARMS.EXE
python3 -m unittest discover -s tests -p test_gp0_matrix_context_cfg.py
ctest --test-dir build -R wa_original_gp0_matrix_context_cfg --output-on-failure
```

Four synthetic test cases exercise alternate entry at a delay-slot
address, unconditional jump behavior, unsupported indirect jumps and
invalid ranges. This is intentionally separate from the earlier
`audit_gp0_matrix_cfg_join.py` analysis: no matrix coefficients or
register sources are yet derived using this graph.

**Verification boundary:** changes are committed and registered with
CTest, but a successful full CI run or audit on the original EXE is
not established. This graph is incomplete and not PlayStation hardware
certification. No original game assets or binaries are committed.

## Stage 174: branch-likely annulment in the context-labelled CFG

Ordinary MIPS branch-likely opcodes 20–23 now produce two alternatives:
the taken path enters a branch-specific delay-slot context and afterwards
jumps to `PC+4+(sign_extend(imm16)<<2)`; the not-taken path skips the
slot and directly enters `PC+8`. Two synthetic cases check both edges.
This applies only to the context-sensitive prototype; the older
context-insensitive CFG still excludes such instructions.

The instruction-specific branch predicates remain symbolic (both paths
are considered possible), and REGIMM likely/link forms are still unresolved.
This is an analysis improvement, not confirmation of exact game execution.
The update was committed without an independently confirmed CI result.

## Stage 175: repaired likely edges and REGIMM likely subset

The stage-174 conditional branch-likely implementation contained a
fallthrough assignment that overwrote the two newly constructed successor
contexts. Stage 175 fixes that defect and adds a regression checking both
successors exist simultaneously.

The shared decoder now recognizes REGIMM `rt=2` BLTZL and `rt=3`
BGEZL as `regimm_likely`. The context-labelled CFG explores taken
execution via its delay slot and not-taken execution via annulment.
Other REGIMM link and unsupported forms remain unresolved; the legacy,
context-insensitive CFG intentionally reports likely branches as unresolved.

The branch predicates are not evaluated; the graph is a conservative
possibility model. Committed tests do not by themselves confirm successful
execution or bit-exact PlayStation geometry.

## Stage 178: COP branch decoding safety

Coprocessor branch instructions (COP0–COP3 with `rs=8`, notably
`BC2F`/`BC2T` on the PlayStation GTE) must not be interpreted as
ordinary fallthrough instructions. The shared decoder now classifies
these as `coprocessor_branch` with an unresolved control transfer.
Both the legacy and context-labelled CFG stop propagation at those
instructions instead of inventing reachable successors.

Synthetic tests assert that a COP2 conditional branch does not emit
linear or fabricated delay-slot edges. GTE branch predicates and full
COP instruction semantics are not modelled yet. Commit of tests is not
a verified successful CI run.
