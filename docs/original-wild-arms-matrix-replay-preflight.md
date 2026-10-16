# Stage 192 — private Wild Arms matrix replay preflight

The new host-only tool `tools/audit_gp0_matrix_replay_preflight.py`
accepts a **privately supplied** extracted `WILDARMS.EXE` file and
examines the previously identified matrix constructor at
`0x800B7118–0x800B739C`. By default, the operation is **static only**.

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight /private/path/WILDARMS.EXE
```

The JSON output contains counts by opcode family, a count of encodings
handled by the current partial MIPS interpreter, counts of missing
families such as COP2/GTE, and whether the known Q12 table address
`0x800CBE44` falls within the loaded image. It does **not** print
opcode words, original executable bytes or table samples.

An optional, explicitly experimental probe is available:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight /private/path/WILDARMS.EXE --explore --max-steps 512
```

It maps the caller-owned PS-X EXE as **read-only** guest memory, adds
a separate writable 18-byte scratch matrix, seeds synthetic zero-valued
general registers except `a1` (matrix pointer), and uses the
bounded MIPS control-flow interpreter. It stops on unsupported MIPS
instructions, invalid memory accesses, a step limit or reaching
the documented return site. The report includes only aggregate step
counts, whether any or all nine matrix offsets were stored, and a halt
reason. It never exposes register values or matrix coefficients.

**Important:** zero-filled synthetic registers are not a valid game
call-site state. Reaching a return site or writing nine offsets is
not proof of matching original gameplay or correct coefficients.
Direct original-EXE execution and hardware comparisons have not
been performed.

## Local verification

The preflight's seven synthetic unit tests were executed in an
isolated local reconstruction of the relevant project modules:
**7/7 passed**. The earlier 25 MIPS control-flow, matrix-memory and
trig-memory tests were also re-run locally: **25/25 passed**.
The limited testing environment used exact builder/table constants
as local module stubs; a complete checkout and GitHub Actions success
were not available. The tests are now connected to CTest and
`matrix-audits.yml`.

The user's original `WILDARMS.EXE` was not available in this turn.
No game binaries or copyrighted table data were committed.

## Stage 193 — bounded synthetic stack and actionable halt categories

The optional `--explore` mode now maps a separate writable 4 KiB
**synthetic** stack at `0x80120000`, seeding `$sp` near its upper
end. This allows ordinary stack-frame `SW/LW` operations in a
controlled replay. It does **not** imply that these stack addresses,
initial register contents or observed execution paths match gameplay.
Memory-region overlap and bounds remain enforced.

To help prioritize missing interpreter features without disclosing
code, the exploratory JSON also reports:

- `executed_instruction_families`: aggregate counts on the visited path;
- `halt_instruction_family`: the generic family at the stopping PC;
- `halt_category`: distinguishes unsupported instructions from mapped
  memory/alignment errors and other execution failures;
- `distinct_matrix_slots_written`: number of different matrix SH slots
  reached, separately from the number of repeated stores;
- `return_instruction_executed: false`: the preflight stops **before**
  the specified return-site PC; reaching the site is not a real function
  return.

No executable opcode values, guest addresses from the dynamic trace,
registers, trig-table samples or coefficient values are exposed.

**Validation:** 10/10 preflight tests (three new: stack prologue,
COP2 blocker and unmapped load) and 25/25 related MIPS/matrix/trig tests
passed locally in the previously reconstructed source tree. Syntax was
also compile-checked locally. A complete private repository checkout,
GitHub CI run and original `WILDARMS.EXE` comparison remain unverified.

## Stage 194 — verify the original caller contract and probe its frame layout

The static preflight now checks two opcode facts at the original caller:
- the `JAL` at `0x80077980` targets the matrix builder at `0x800B7118`;
- the instruction at `0x80077970` computes `$a1 = $sp + 16`.

The `caller_linkage` JSON contains only booleans. When the call site
is missing from an incomplete load image, all flags are false. No
original instruction words or register values are output.

The **opt-in** frame-layout probe can use the caller's observed pointer
relationship instead of a separate matrix allocation:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --explore --frame-layout --max-steps 512
```

In this mode a bounded synthetic 4 KiB scratch stack is mapped,
`$sp` is seeded near its upper edge, and `$a1 = $sp + 16`.
The 18-byte matrix is written **inside that stack region**, so a
second overlapping mapping is not needed. Attempts to override
`$a1` or `$sp` via the probe's Python API are rejected in this mode.
The former independent matrix mapping remains the default for
backward compatibility.

The probe reports `frame_layout: "a1_sp_plus_16"` or
`"separate_matrix"` and the count of distinct matrix halfword slots
written; it does not emit the stack address or coefficient contents.

**Verification:** Seven new synthetic tests cover confirmed and
rejected caller linkage, missing call site, all nine `SH` matrix
writes on the scratch stack, `sp+16` aliasing, conflicting register
overrides and backward compatibility. In a locally reconstructed
source environment, the related complete suite passed **42/42**:
the earlier 35 tests plus seven new ones. This is **not** a confirmed
GitHub Actions run, and neither the original `WILDARMS.EXE` nor
hardware output has been exercised. Inputs remain synthetic.

## Stage 195 — replay the caller JAL and verify the builder's JR return

An additional **opt-in** mode now begins at the caller's argument
setup instruction (`CALL - 16`) rather than directly at the builder
entry. It requires the known caller opcodes to pass validation before
execution. The interpreter follows the actual `JAL` and its delay
slot into the builder and runs until it **returns to `CALL + 8`**,
or until a bounded/unsupported-operation halt:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-replay --max-steps 4096
```

`--caller-replay` implies exploratory execution and the `a1=sp+16`
stack-resident synthetic matrix layout. The caller's `ADDIU a1,sp,16`
instruction must actually execute; the harness does **not** inject the
matrix address into `$a1` in advance.

The sanitized `exploratory_trace` now also reports
`replay_origin`, `caller_jal_executed`,
`builder_entry_reached`, `return_instruction_executed` and
`returned_to_caller`. A reported return requires that a `JR $ra`
executed immediately before its delay slot, that the `JAL` and the
builder entry were visited, and that execution stopped at the
caller's continuation. A direct `J` to the continuation is **not**
accepted as a genuine function return.

Four new synthetic tests cover JAL → nine matrix halfword stores →
JR return, wrong JAL target, a deceptive direct jump to the return
address, and an unsupported COP2 opcode at builder entry. Existing
preflight and MIPS/trig tests were also run on the local source
reconstruction: **46/46 passed**, and Python compile-check passed.
The new cases reuse the existing test filename already registered in
CTest and GitHub Actions, so no workflow changes are needed.

These tests are synthetic and cannot establish original Wild Arms
numerical outputs. Original executable bytes, guest register values,
table samples and matrix coefficients remain excluded from reports.
No full checkout CI success or real-device execution is claimed.

## Stage 196 — completed control transfers and strict return proof

Prior inference based on the last two visited instruction addresses
could misidentify a return. A `JR $ra` instruction at the expected
builder return site is **not** a completed return if its delay-slot
instruction fails. An earlier return can also reach the caller without
ever executing that expected final return site.

The bounded interpreter now records internal
`control_transfers = ((branch_pc, kind, resolved_target), ...)` only
when a transfer has truly completed. In particular, a normal branch,
`JAL`, `J`, `JR`, or `JALR` contributes a completed transfer **after
its delay slot finishes successfully**. Non-taken branch-likely
instructions with annulled slots record the immediately resolved
transfer. A failed delay slot does not add a completed transfer.
These addresses remain internal to the emulator and are **not**
included in the public preflight JSON.

`returned_to_caller` now demands that the actual `JAL` at the
verified caller site resolves into the builder AND the expected builder
return instruction completes a `JR $ra` transfer to the caller
continuation. The separate `return_instruction_executed` status also
requires that expected `JR $ra` transfer to complete, not merely be
encountered. An early unrelated `JR` does not satisfy the criterion.

The decoder additionally rejects malformed `BLEZ/BGTZ` variants
whose reserved `rt` field is not zero, and the preflight's static
instruction-family checker agrees.

Six new regression tests cover successful transfer recording,
a failed delay-slot transfer, malformed BLEZ encoding, a JR with a
failing delay slot, an earlier non-final JR and reserved-field
classification. In the locally reconstructed source tree, the
existing 46 tests plus these six passed: **52/52**, as did Python
`compileall`. Full original-game execution, real-device comparison,
and successful GitHub Actions CI are still not verified.

Run on a checkout:

```sh
python3 -m unittest discover -s tests -p test_mips_control_flow.py -v
python3 -m unittest discover -s tests -p test_gp0_matrix_replay_preflight.py -v
```

## Stage 197 — infer missing entry register inputs from executed MIPS paths

`tools/mips_entry_dependencies.py` adds deterministic *read-before-write*
analysis over the instruction addresses returned by the concrete MIPS replay.
The result is a sorted list of **register numbers only**: a register is
reported when an executed instruction reads its value before any earlier
executed instruction established a new value.

The analysis handles source/destination registers of supported integer
ALU, shifts, branches, jumps, stores, and loads. It explicitly honors the
R3000A **one-instruction load delay**: an instruction immediately following
`LW/LH/LB` reads the previous destination-register value and may therefore
introduce a new input dependency. It also honors the result of a load
being superseded by a following write to the same register. JAL/JALR
register-link writes are included in the sequence.

When `--explore` or `--caller-replay` runs, the safe JSON summary
now includes `exploratory_trace.read_before_first_write_gprs`, for example
`[4, 29]` on a **synthetic** caller that consumes an uninitialized
`$a0` and bases `$a1` on `$sp`. The list does not contain register
**values**, original game machine words, trigonometric entries, or
output matrix coefficients.

This is *path-dependent* and *conservative*: it does not analyze
unvisited branches, memory aliasing or HI/LO initial values, and
does not prove that a listed initial register influences a specific
coefficient. Some registers, such as `$sp`, are deliberately seeded
with synthetic values. A future private-original-EXE run should use
the results to prioritize obtaining concrete calling-state samples,
not to assume zero-seeded input values are authoritative.

**Local verification:** The 10 new unit tests cover immediate and
delayed register writes, `LW` followed by ALU or branch, consecutive
loads, stores, jumps, negative/out-of-image cases and skipped paths.
Two additional integration tests exercise the safe preflight JSON and
the caller's `$a1 = $sp + 16` relationship. All **64/64** tests
in the locally available 17 Python files passed, and
`python3 -m compileall -q tools tests` completed successfully.
This is a relevant-module checkout, not a complete GitHub Actions
or Nintendo Switch verification. The original user-owned game
executable was not available for numerical comparisons.

To rerun:

```sh
python3 -m unittest discover -s tests -p test_mips_entry_dependencies.py -v
python3 -m unittest discover -s tests -p test_gp0_matrix_replay_preflight.py -v
```

## Stage 198 — privacy-safe differential probes of caller inputs

A new opt-in `--input-sensitivity` flag executes the previously validated
`--caller-replay` entry path four times against a **fresh** synthetic
stack each time: baseline, then a single perturbation to `$a0` (GPR 4),
`$a2` (GPR 6), and `$a3` (GPR 7). The caller's stack and `$a1=$sp+16`
relationship are preserved; neither `$sp` nor `$a1` is perturbed.

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE \
  --caller-replay --input-sensitivity --sensitivity-delta 1 \
  --max-steps 4096
```

The `input_sensitivity` result reports which GPR was perturbed;
whether the guest execution path or set of matrix stores changed;
whether both executions genuinely returned through the expected
`JR $ra`; and, **only if both returned and wrote all nine SH slots**,
how many signed-16 matrix coefficients differ (0–9).

The actual nine coefficients, guest register values, private table
entries, code bytes and dynamic addresses are **never printed**.
An interrupted run or partial matrix always produces
`changed_coefficient_count: null`, not a misleading comparison.
A zero difference for a one-step perturbation is **not** proof of
independence; other seeds, input increments or branch paths could
yield a different outcome. This is a synthetic sensitivity test,
**not** known gameplay calling-state reconstruction.

Seven tests in the new pure module and four integrated preflight tests
cover complete and incomplete matrices, changed control flow, safe
summary structure, independently mapped memory, a synthetic nine-slot
builder using `$a0`, a caller-only mode guard and an artificial PS-X
image containing a synthetic Q12 sin/cos table. The locally available
project subset ran **75/75 tests** (64 earlier tests plus 11 new ones),
and Python `compileall` passed. The related CI workflow and CTest
entry were extended; successful remote GitHub Actions and Switch
hardware execution have not been verified.

The exact user's original `WILDARMS.EXE` remains unavailable in
this session. Thus no conclusion about actual coefficient sensitivity
in the original game has been established.
