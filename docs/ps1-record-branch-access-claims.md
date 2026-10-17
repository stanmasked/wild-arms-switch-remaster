# Stage 237 — bounded MIPS BEQ/BNE claimed-PC sequence validation

Earlier stage 236 correlates **privately claimed** straight-line MIPS
instruction PCs, user-owned PS-X EXE opcode bytes, pointer-relative
memory accesses, and addresses at two or three code sites. That tool
remains **linear-only by default**.

Stage 237 adds `tools/mips_record_branch_trace.py` and a separate
read-only command `tools/audit_record_branch_access_claims.py` to
extend this **self-consistency** check to restricted PS1 branch
sequences. It uses the same private EXE and version-linked SHA-256,
sample format, cross-site address checks, and sanitized reporting.

## Exactly what is modeled

- The first eleven index/pointer-load instructions must appear in
  their exact sequential order. The checked-in prefix includes a
  `LW` followed by an independent `SLL` before potential pointer
  arithmetic. This verifies only the **static load-delay gap**, not
  cycle-exact load forwarding or hardware register values.
- Only standard (not likely) `BEQ` and `BNE` branches are accepted
  in the next ten instruction slots. A claimed PC sequence **must
  include the branch's immediately following instruction**: a literal
  NOP delay slot. The next PC must be the actual encoded forward
  target or normal fallthrough and must remain in the bounded window.
- A same-register `BEQ r,r` can only take the target; same-register
  `BNE r,r` can only fall through. For other operands both choices
  are syntactically possible. **The tool never authenticates the
  actual predicate or branch choice.**
- Only optional NOPs, one supported index-preserving `ADDU`, and
  then one direct `v1`-based load/store with the declared signed
  displacement and required alignment can complete a candidate.
- Branch-likely, J/JAL/JR/JALR, backward or out-of-window branches,
  control instructions in a non-NOP delay slot, missing PC entries,
  extra unsupported arithmetic, overwritten pointers and unexpected
  memory operations are **not inferred**. Such claim sequences are
  considered unsupported or contradictory.

The report includes counts of valid claimed instruction sequences,
checked NOP delay slots, and branches whose register comparison was
unknown. The pre-existing 2–3-site, 3-or-more-common-indices,
stable-claimed-base and pairwise effective-address checks still apply.

## Private use

```sh
python3 -m tools.audit_record_branch_access_claims \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/record-access-capture.json
```

Use the private stage-236 input schema
`wild-arms-ps1-executed-record-access-claims-v1` (see
`docs/ps1-executed-access-claims.md`), including the **actual
claimed-PC path with any mandatory branch delay-slot PC**, not an
expanded linear PC list.

For a valid self-consistency match the process exits 0. For a
well-formed but mismatching trace or address it exits 1. Invalid,
missing or oversized private input returns 2 with only the generic
`invalid_private_input` JSON error. No game bytes, addresses,
instruction opcodes, original EXE SHA, debugger registers, local
filenames or per-site private details are included in reports.

## Verification boundary

Matching a user-supplied branch path to opcode targets **does not
prove** the debugger really observed that path. Register predicates
could depend on unobserved RAM contents, interrupts, pending loads,
or original game inputs. This audit does not model all PS1 pipeline
corners, hardware provenance, runtime self-modifying code, KSEG alias
behavior, allocator boundaries, or the actual in-game record size.

The instruction-derived coefficient 2708 is not an authenticated
structure stride; the old 364 claim remains unsupported; an
independently studied 88-byte record belongs to another code site.
Native Nintendo Switch game execution has not been established.

Synthetic regressions check both branch outcomes, same-register
predicates, mandatory NOP delay slot, invalid PC targets, unsupported
opcodes, branch encoding mutation, field alignment, cross-site data
relationships, non-leaking private CLI and **backward compatibility
of the stage-236 linear mode**. CI verifies synthetic tool behavior
only; no original PS1 capture or game asset is committed.
