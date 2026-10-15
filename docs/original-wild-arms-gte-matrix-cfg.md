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
