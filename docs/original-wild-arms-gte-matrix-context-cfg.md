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
