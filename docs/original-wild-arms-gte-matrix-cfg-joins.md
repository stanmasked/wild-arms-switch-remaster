# Wild Arms rotation constructor — stage 164: CFG provenance joins

A new host-only auditor, `tools/audit_gp0_matrix_cfg_join.py`,
propagates symbolic lookup source addresses along the direct edges supported by
`audit_gp0_matrix_cfg.py`. At joins, it computes a **may-depend-on union**:
a store can report several candidate lookup PCs from different possible
incoming paths. A worklist converges in loops because the source sets are
finite and only grow.

Supported computations include moves through immediate integer operations,
simple shifts, common register-register ALU operations and explicit LW
definitions. Overwriting a register discards its earlier provenance. Only
known original lookup addresses become source labels. The report does not
copy original lookup data or executable instruction words.

Usage (requires a privately extracted game executable):

```sh
python3 tools/audit_gp0_matrix_cfg_join.py /private/path/WILDARMS.EXE
python3 -m unittest discover -s tests -p test_gp0_matrix_cfg_join.py
ctest --test-dir build -R wa_original_gp0_matrix_cfg_join --output-on-failure
```

The synthetic tests exercise branch joins, killed sources, unreachable stores,
indirect-transfer boundaries and invalid images.

## Interpretation limits

- A reported source is **possibly** upstream of an SH, not necessarily
  executed on a reachable hardware branch condition. Branch outcomes are
  intentionally nondeterministic.
- HI/LO values and MUL/MULTU dependency chains are not carried in this pass.
- The predecessor merge uses register source sets, not precise value
  semantics; calls, indirect jumps and branch-likely transfers are unresolved.
- Delay slots appear in the CFG, but edge-specific state and atypical branch
  instructions inside slots are not fully modelled. This is not a complete
  emulator or sound certification of the game's matrix algorithm.
- No bit-exact GTE coefficients, rounding rules or full original-EXE
  execution have been certified; CI execution remains to be verified.

The follow-on task is an edge-sensitive CFG representation that separates
delay-slot contexts, along with HI/LO propagation and branch predicates.

## Stage 165: HI/LO source propagation

The CFG-join transfer state now includes two additional symbolic registers,
HI (index 32) and LO (index 33). Valid R-type `MULT`/`MULTU` replace
both with the union of operand source labels; `MFHI`/`MFLO` copy
the corresponding source to the destination GPR; `MTHI`/`MTLO`
explicitly overwrite the corresponding source. The worklist merges these
source sets alongside the 32 general registers.

Four further synthetic tests check signed and unsigned multiplication,
overwriting an earlier product, and explicit MTLO-to-MFLO propagation.

**Caution:** source labels are not 64-bit arithmetic values. This stage does
not establish multiplication overflow, signedness of the coefficient formula,
MIPS pipeline timing or actual branch predicates. The CFG remains context-
insensitive regarding delay slots, calls and unresolved branch types. The
output remains a *may-source* diagnostic, not a bit-exact matrix reconstruction.
The private original EXE is not included, and complete CI execution has
not been confirmed.
