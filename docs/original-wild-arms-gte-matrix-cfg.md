# Stage 163: MIPS control-flow skeleton for Wild Arms matrix construction

The new `tools/audit_gp0_matrix_cfg.py` emits a conservative control-flow
edge inventory for the original builder at `0x800B7118..0x800B739C`.

Direct conditional BEQ/BNE/BLEZ/BGTZ and selected REGIMM branches produce
an instruction-to-delay-slot edge, followed by edges from the slot to the
taken target and fallthrough. Direct J emits its target after its delay slot.
A direct JAL is intentionally unresolved because a call requires modelling
its return, link register and callee effects. JR/JALR and branch-likely
are unresolved. Edges leading outside the audited range are reported rather
than silently followed.

Unlike an ordinary sequential listing, a delay-slot instruction has no
implicit fallthrough edge: that edge would spuriously make the CFG treat an
unconditional jump as conditional. Executable branch instructions that
themselves appear in a delay slot remain outside the supported control
model and must not be interpreted as certified.

Run:

```sh
python3 tools/audit_gp0_matrix_cfg.py /private/path/WILDARMS.EXE
python3 -m unittest discover -s tests -p test_gp0_matrix_cfg.py
ctest --test-dir build -R wa_original_gp0_matrix_cfg --output-on-failure
```

Eight synthetic tests cover positive and negative branch offsets,
jump target reconstruction, explicit delay edges, unresolved calls,
indirect jumps, branch-likely instructions and invalid image ranges.

**Evidence limit:** This is not a complete CFG, not inter-block
register-provenance propagation, and not a reconstruction of the nine
matrix coefficient formulas. Neither original game code nor assets are
included in the source files or test fixtures. The test suite was
registered with CTest; its execution and full CI status are not yet
verified in this stage.

Next: add explicit predecessor merges, branch-sensitive provenance
and delay-slot-aware register semantics; verify candidate lookup-to-SH
chains against the user-owned executable.

## Stage 166: unsupported REGIMM safety

A previously unrecognized REGIMM branch variant (opcode 1 with an rt
subopcode outside the explicitly supported set) could accidentally be
classified as linear, introducing an unsound fallthrough path.

Such opcodes now produce an unresolved transfer, without speculative
post-delay-slot outgoing edges. A synthetic BLTZL test checks that the
post-slot fallthrough is not inferred. This does **not** implement
branch-likely delay-slot annulment and does not establish a complete CFG.

The analysis remains conservative and incomplete until edge-sensitive
delay-slot execution and actual MIPS branch predicates are modelled.

## Stage 167: branch-link and delay-slot guardrails

The CFG decoder now refuses to treat REGIMM link forms (BLTZAL/BGEZAL)
as ordinary branches. Their link-register semantics are not modelled in
the symbolic register analysis, so the auditor reports them as unresolved.

A control transfer syntactically located in the delay slot of another
control transfer is reported as unsupported, rather than generating nested
jump edges. Malformed JR/JALR encodings with reserved fields are not treated
as valid indirect jumps. Three synthetic tests were added.

These safeguards deliberately trade completeness for reduced false paths.
They do not yet certify the entire MIPS CFG or any original rotation
coefficient values. Tests are committed, but their execution in CI remains
unverified.

## Stage 168: annulled delay-slot safeguards

MIPS branch-likely instructions (opcodes 20–23) can annul their delay
slot on the not-taken path. The old graph unconditionally included an
edge from the branch to its delay slot, creating false may-dependencies.

The CFG now emits **no executable edge** for unsupported branch-likely
or unsupported REGIMM forms, and records the corresponding unresolved
transfer. This is intentionally incomplete: it avoids incorrectly
asserting unconditional slot execution but does not prove reachability
for a taken path. Two synthetic regression cases cover these edges.

No original game executable or trigonometric samples are committed.
The GitHub changes are written, but a successful native CI run is
not yet verified.
