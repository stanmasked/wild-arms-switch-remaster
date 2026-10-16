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

## Stage 199 — separate caller-prepared from unresolved matrix inputs

The new host module `tools/mips_call_boundary.py` splits an **executed**
MIPS caller replay at the first visited builder entry address. It
computes which general-purpose registers the builder path reads before
writing them, then checks which of those have already been prepared by
instructions in the caller prefix (including `JAL` and its delay slot).

The optional `--caller-replay` preflight JSON includes a sanitized
`exploratory_trace.call_boundary` structure with:

- `builder_entry_reached`: whether the builder's first instruction
  was actually *executed*, not just targeted by JAL;
- `builder_read_before_write_gprs`: register-number dependencies on
  the executed builder path;
- `builder_inputs_prepared_by_caller`: dependencies whose values were
  written by the executed caller prefix;
- `builder_inputs_unresolved`: dependencies not established by the
  observed caller prefix;
- `pending_load_at_entry_gpr`: a caller load destination still in its
  MIPS one-instruction load-delay window, or null.

All arrays contain **GPR numbers only**. No initial values, matrix
coefficients, executable instructions or original trigonometric data
are emitted. This is **not** complete value provenance: builder-side
load delays, initial HI/LO, memory aliases, and unexecuted branches
can limit the conclusions. A register listed as unresolved may have a
legitimate incoming gameplay value supplied by an outer caller;
a pending load should not be assumed ready on the first builder
instruction.

For example, in a synthetic caller that executes
`ADDIU a1,sp,16; JAL builder; NOP`, followed by a builder that
reads `a0` and `a1` before its return, GPRs 5 (`a1`) and
31 (`ra`) are attributed to the caller while GPR 4 (`a0`)
remains an external/unresolved input. If the first builder opcode
fails (such as unsupported COP2), the report explicitly marks the
entry as **not executed** and does not invent dependencies.

Verification in the local `wa198` source reconstruction:
**86 of 86 tests passed** (75 previously tested plus 9 standalone
call-boundary regressions and 2 preflight integration tests).
`python3 -m compileall -q tools tests` passed. This is a
subset checkout: a full GitHub Actions run and a test with the
user-owned original `WILDARMS.EXE` are not verified. Both CTest
and the CI workflow have been updated to run the nine new tests.

## Stage 200 — trace the source of a0–a3 before the JAL

The host module `tools/mips_caller_sources.py` now inspects a **bounded,
straight-line instruction window ending with the caller's JAL delay
slot**. Its `caller_argument_sources` output is included in both static
and exploratory preflight JSON; no private game bytes or numeric values
are emitted. The default inspection window is four instructions before
the JAL. It can be extended manually:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-lookback 12
```

Each argument register (GPR 4–7) is classified as an incoming GPR,
stack-pointer-derived value, literal-derived value, computed value,
or memory-derived value. Memory loads are further classified as
stack-relative, constant-address or indirect. The report includes
only upstream GPR numbers, category labels, and an explicit indicator
for loads *still pending* at the call boundary. It never includes
constant immediates, addresses, raw opcode words, initial register
contents, packed sine/cosine data, or output matrix coefficients.

The analysis recognizes a conservative subset of ALU operations,
LUI/ORI constant construction, GPR moves/shifts, HI/LO transfers,
and aligned memory loads. It models the single-instruction MIPS
load delay, including writes in the JAL delay slot. Reads of HI/LO via
MFHI/MFLO fail closed unless this window establishes the relevant
special register with MULT/MTHI/MTLO; its unknown incoming value is
never silently presented as a confirmed argument source. If the window
contains a branch, coprocessor opcode, or other unsupported
instruction, it reports `window_usable: false` and refuses to
invent argument origins.

**Critical limitation:** the report always has
`runtime_path_confirmed: false`. It describes *what the decoded
straight-line bytes would do if reached sequentially*. A wider
lookback can cross a real control-flow entry or a preceding delay
slot; such cases require separate dynamic/CFG validation. An
`incoming_gpr` means only that the register's origin is outside
the scanned window, not that it has no meaningful game value.

A 4-instruction window sees the established `a1=sp+16` operation
when present. A wider synthetic window correctly identifies an
earlier preparation of `a0` from `a2`. Unsupported branches
deliberately invalidate the inference rather than yielding
misleading sources.

**Verification:** The local source test environment in
`/mnt/data/wa200` ran **112/112 synthetic unit tests** including
23 new source-provenance cases and 3 new preflight integration
cases, alongside the prior 86 tests. Python compile-check completed
without errors. The source module and standalone 23-test suite
were additionally verified against the GitHub file blob hashes.
CTest and the matrix-audits GitHub Actions workflow now include
the new tests. A successful full CI run, private original
`WILDARMS.EXE` evaluation, exact nine-coefficient comparison,
and Nintendo Switch hardware execution are **not confirmed**.

## Stage 201 — bounded path-sensitive MIPS caller CFG

The new module `tools/mips_caller_cfg_sources.py` can conservatively
enumerate alternative conditional paths through a caller's pre-JAL
instruction window. Unlike the old straight-line analysis, it handles
supported `BEQ`, `BNE`, `BLEZ`, `BGTZ`, `BLTZ`, and `BGEZ` paths,
executes their delay slots, tracks the one-instruction load delay, and
evaluates branches with provably known constants or equal-register
predicates. Unknown conditions explore both paths.

It is available as an explicitly opt-in preflight mode:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-cfg --caller-lookback 12
```

The `caller_argument_cfg` field reports counts of complete paths to
the call and safe aggregate sources for `a0`–`a3`. If different
paths establish different argument origins, both are retained:
`source_kinds`, `incoming_gprs`, and `memory_kinds` are sorted
unions, while `same_origin_across_paths` is false. A pending load
in any path is marked `load_pending_on_any_path`.

The analysis deliberately refuses to make claims when branches leave
the inspected window, loops or branch-in-delay-slot patterns are found,
unsupported instructions occur, or the state/path bounds are exceeded.
It does not silently discard a problematic path. The default static
`caller_argument_sources` output remains present; the CFG variant is
absent (`null`) unless requested.

**Important limitations:** This is a bounded static path exploration,
not recorded game execution. `runtime_path_confirmed` and
`external_entry_edges_ruled_out` are always false. An unknown
indirect jump or an entry from outside the window can change which
instructions are actually reached. The tool does not print original
machine words, numeric arguments, addresses discovered during tracing,
trigonometric entries, or matrix values. MIPS branch-likely and jump
instructions before JAL are not modeled; those paths fail closed.

**Verification:** 17 standalone CFG unit tests plus three preflight
integration tests were added to the previously passing 112-test
local source subset, for **132/132 passing Python tests**. Byte-for-byte
Git blob hashes for the new module and its test suite match the local
copies executed. `compileall` passed. CTest and `matrix-audits.yml`
were extended to include the new tests. Successful complete GitHub
Actions CI, a real `WILDARMS.EXE` analysis and Switch device
execution remain unverified.

## Stage 202 — correlate executed caller paths with CFG alternatives

The bounded caller CFG analyzer now accepts an optional in-memory
`observed_pcs` sequence from `mips_control_flow.execute`. Every
statically enumerated path retains its executed instruction order
including conditional-branch delay slots, the `JAL` and the JAL's
delay slot. When the observed path exactly matches one or more
enumerated paths, it reports `synthetic_probe_path_matched: true`
and only the register-source descriptions for those matched paths.
The aggregate static `arguments` remain available independently.

No path addresses or instruction words are emitted in JSON. The
new safe fields are:

- `synthetic_probe_path_supplied`
- `synthetic_probe_window_covered`
- `synthetic_probe_path_matched`
- `synthetic_probe_matching_path_count`
- `synthetic_probe_argument_sources` (GPR numbers and origin categories)

**Critical distinction:** `runtime_path_confirmed: false` remains
unchanged. Path matches refer only to the bounded **synthetic** MIPS
runner, not real PlayStation gameplay, and external CFG entry edges
are not ruled out.

A four-instruction caller replay (the legacy default) can correlate
automatically against a four-instruction CFG window when both
`--caller-replay` and `--caller-cfg` are enabled. If the static
window is larger than the actually executed caller prefix, the
probe explicitly reports *no match* rather than inventing coverage.

For a longer static window, an additional **explicit opt-in** permits
the synthetic runner to start from the same entry as the CFG window:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE \
  --caller-cfg --caller-replay \
  --caller-lookback 8 --replay-cfg-window --max-steps 4096
```

`--replay-cfg-window` requires both caller replay and CFG analysis,
and a lookback of at least four instructions. An invalid static CFG
window is rejected before extended replay starts. The opcode
validation of the original caller JAL and `a1=sp+16` remains in
place; a longer synthetic window may still fail during bounded
execution because of unsupported ops, invalid memory or uncertain
input state.

The integrated synthetic fixture contains a pre-call `BEQ`:
one path keeps the incoming `a0` value; the other executes an
`ADDIU` deriving `a0` from `a2`. Both paths are statically
enumerated, but with different seeded registers the concrete runner
selects one and reports **only its** safe source categories. Tests
also cover incomplete windows, delay-slot omission, missing paths,
static-only behavior, invalid options, unsupported CFG instructions
and correct command-line forwarding of the new mode.

**Verification:** 15 new local tests (seven path matcher, eight
end-to-end/CLI) added to the previous 132: **147/147** synthetic
Python tests pass in the relevant-module local source checkout.
`python3 -m compileall -q tools tests` also passes. The new
test files are registered in CTest and GitHub Actions. No complete
GitHub Actions success, original `WILDARMS.EXE` runtime,
bit-exact PS1 matrix coefficient comparison or Switch hardware
execution has been confirmed.

## Stage 203 — identify successful Q12 table and stack loads without disclosing values

The bounded integer interpreter now records *successful* concrete memory
loads internally as `(instruction_pc, resolved_address, byte_width,
destination_gpr)` tuples in `execute(...).load_accesses`. These raw
guest addresses are strictly for local testing and in-memory analysis;
they are **not** added to the user-facing preflight JSON. Failed loads,
annulled branch-likely slots and instructions that never execute create
no load event. A successful load in a completed JR delay slot is
correctly included. Existing one-instruction R3000A load-delay
behavior is unchanged.

The host module `tools/mips_load_access_profile.py` converts the raw
events to a **sanitized, aggregate** profile. An opt-in
`--explore`, `--caller-replay` or `--replay-cfg-window` preflight
includes it as `exploratory_trace.memory_read_profile`.

It reports total successful loads; aggregate reads from the protected
18-byte matrix, scratch stack, other PS-X EXE data and the packed
Q12 table; number of *distinct* 32-bit trig-table entries reached;
and count of known original lookup instruction sites that executed a
genuine packed table LW. Reading at a known code site is counted as a
trig lookup **only if the dynamically resolved address is inside
the correct packed table**. Partial LB/LH table accesses are tracked
separately, not misrepresented as complete sin/cos entries. Only
destination GPR numbers, counts and booleans are exported.

Example (private EXE, explicitly synthetic registers):

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-replay --max-steps 4096
```

The JSON always states
`original_rotation_angles_recovered: false` and
`private_values_emitted: false`. **This is not recovery of gameplay
angles or coefficients.** A packed table index may reveal which
synthetically seeded angle was used in the concrete runner; it is not
a proven input from a real PS1 save/game state. No indices, addresses,
table entries or original register contents are printed.

For verification, 12 standalone memory-profile regression cases test
real LW/LH replay, unique/repeated Q12 table entries, special matrix
and stack regions, ignored failed reads, skipped delay slots, successful
JR-delay-slot loads and the distinction between known lookup *sites*
and actual table addresses. Four more integration tests run the
private-EXE preflight API on a **fully synthetic PS-X EXE** containing
synthetic cardinal Q12 entries and a LUI/LW table lookup, plus stack,
failed-load and static-only cases.

The relevant local source subset passed **163/163 Python tests**
(previously 147, plus 16) and `python -m compileall -q tools tests`.
The three new source/test files match their GitHub Git-blob hashes.
CTest and GitHub Actions were extended with the two new test suites.
This is **not** a confirmed full GitHub Actions run or original
`WILDARMS.EXE` replay; exact PlayStation matrix equality and
Nintendo Switch hardware operation remain unverified.

## Stage 204 — executed index-address provenance for packed Q12 sine/cosine

The new `tools/mips_trig_index_provenance.py` performs **shadow
dependency tracking** over instruction addresses actually visited by
the bounded MIPS interpreter and its separately recorded **successful**
load events. A table lookup is counted only if the concrete `LW`
accessed a 4-byte-aligned entry inside the mapped packed Q12 table.
Recognizing a code pattern alone is not enough.

The analysis tracks the register numbers on which the **effective
address** depends, including a conservative lineage across ALU
instructions, the 12-bit `ANDI 0x0FFF` mask, `SLL` by two bits,
`ADDU`, `LUI` and preceding memory loads. It mirrors the PS1
one-instruction load-delay contract: an instruction immediately
following `LW` still sees the previous register value. When a
subsequent instruction writes the same destination, it supersedes a
pending load. Successful reads at repeated PCs (loops) are
matched in execution order, and inconsistent traces are rejected.

The private preflight's optional exploratory report contains
`exploratory_trace.trig_address_provenance`:

- `packed_table_loads_with_provenance`: actual successful packed LW
  events checked;
- `address_dependency_gprs` and
  `address_dependency_lookup_counts`: **register numbers and counts
  only**, not initial register values;
- counts for lookup address chains containing a left shift by two,
  a 12-bit mask, or an earlier memory read;
- counts with unknown provenance or without external address roots;
- explicit `original_angle_values_recovered: false`,
  `input_gpr_proven_to_be_game_angle: false` and
  `private_values_emitted: false`.

**Important distinction:** an input GPR can carry a *pointer to the
table* rather than an angle, and an observed mask/shift in an address
chain does not by itself prove what the original gameplay angle was.
The analysis reports potential dependencies of addresses, not
complete symbolic identities or bit-exact source values. It is still
based on synthetic caller register state unless original game state
has been supplied and validated separately. No original angles,
table indices, raw addresses, opcode words, matrix values or original
executable bytes are emitted.

Test coverage includes a synthetic
`ANDI a0,0x0FFF → SLL index,2 → LUI base → ADDU → LW` chain,
two-step delayed loads, load overwrite, previous stack-sourced data,
literal table pointers, invalid event streams, repeated same-PC reads
and fail-closed nonexistent loads. Four integration tests run the
preflight on a completely artificial PS-X EXE with a sparse synthetic
Q12 sine/cosine table.

**Verification:** in the local relevant-module source tree
`/mnt/data/wa204`, **178/178** Python tests passed (163 earlier
plus 11 module tests and 4 integration tests); Python `compileall`
also passed. New module and its 11-test suite match their GitHub Git
blob checksums. CTest and GitHub Actions registrations were updated.
A successful full remote CI run, original `WILDARMS.EXE` evaluation,
actual nine-coefficient PS1 comparison and a playable Switch NRO
are **not yet verified**.

## Stage 205 — packed Q12 values into the nine matrix halfword slots

The new `tools/mips_matrix_value_lineage.py` goes beyond the address
provenance established at stage 204. It replays **data dependence** over
the exact instruction PCs, successful load events and successful store
addresses already produced by the bounded MIPS interpreter.

Every genuine aligned 32-bit load from the packed Q12 table receives
a private *event identity* (not an exposed index or address). The
shadow interpreter follows these identities through MIPS GPR ALU
operations, shifts, `MULT/MULTU` into HI/LO, `MFHI/MFLO`, and
`MTHI/MTLO`. It honors the one-instruction R3000A load delay,
including loads overwritten in the immediately following instruction.
A byte-level shadow of previously written memory preserves lineage
across explicit stack spills and re-loads, conservatively marking
unknown/uninitialized external bytes as unresolved.

Only **successful final `SH` stores** at the nine halfword matrix
offsets 0,2,...,16 are attributed to matrix output. A later `SH`
replaces the previous lineage; any overlapping `SB` or `SW` clears
the older SH-output claim for the affected coefficient. Failed loads,
skipped branch-likely delay slots, unexecuted writes and unrelated
Q12 reads do not create false output evidence.

With `--explore` or `--caller-replay`, the safe preflight JSON now
contains `exploratory_trace.matrix_value_lineage`, including:

- total observed packed Q12 loads and number of distinct observed
  lookup events that actually contribute to final matrix slots;
- counts of the nine SH slots written, slots retaining packed-Q12
  data lineage, slots passing through MULT/HI/LO or a memory roundtrip,
  and slots with unresolved external data contributions;
- nine fixed slot indices with booleans and contributing lookup
  *counts*, not any matrix values;
- `gameplay_angle_values_known: false`,
  `bit_exact_ps1_matrix_math_proven: false` and
  `private_values_emitted: false`.

Example invocation with privately owned extracted executable:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-replay --max-steps 4096
```

**Proof boundary:** taint/dependency tracking is conservative rather
than symbolic bit-exact evaluation. Arithmetic cancellation can yield
a mathematically constant result even when a Q12 taint still reaches
the output. Missing taint from a given table load does not prove a
coefficient has no trigonometric dependence along other paths or from
different initial game state. Nor does nine-slot taint coverage prove
that the original game has been successfully executed or that its
coefficient values match PS1 hardware.

**Verification:** in the available locally reconstructed source tree
`/mnt/data/wa205`, **200/200** synthetic unit/integration tests
passed and Python `compileall -q tools tests` succeeded. This adds
18 new shadow-value-lineage tests and 4 synthetic PS-X EXE preflight
integration tests to 178 earlier tests. The three newly published
files' Git blob hashes exactly match the locally tested copies.
The full repo's GitHub Actions and Switch console/hardware results
are not confirmed. No original `WILDARMS.EXE` bytes were uploaded
or published.

## Stage 206 — independently verify synthetic PS1 Q12 arithmetic bit-for-bit

To distinguish **data lineage** (stage 205) from actual integer
arithmetic behavior, stage 206 adds a **separate independent integer
oracle** `tools/mips_q12_arithmetic_reference.py`. It deliberately
does not import the concrete MIPS interpreter's fixed32 helpers.

The oracle specifies exact behavior for *synthetic* MIPS schedules:

- `LH`: signed 16-bit extension into the 32-bit operand register;
- `MULT` versus `MULTU`: signed versus unsigned 32 × 32 product,
  with independent verification of the HI and LO register words;
- `MFLO`: only the low 32 bits of the product are retained;
- `SRA 12`: arithmetic (sign-extending) right shift that rounds
  a negative fractional quantity toward negative infinity;
- `ADDU`: 32-bit wraparound without trapping on overflow;
- `SH`: only the low **16 bits** of the final computed result are
  committed to each output matrix slot.

A crucial overflow example: with both signed LH operands equal to
`-32768`, the raw product is `1073741824`; after `SRA 12`
it becomes `262144`, but the final `SH` writes **zero** because
`262144 & 0xffff == 0`. This differs from treating the matrix
coefficient as an unbounded Python integer.

Two precisely specified three-product dot schedules are tested
separately:

1. **shift after sum:** add all three MFLO words modulo 2³² and
   shift the wrapped accumulator right by 12 once;
2. **shift each product:** arithmetic-shift each MFLO word right by
   12 and then add the three shifted words modulo 2³².

These alternatives can differ. For example, three terms each equal
to `-1` result in **-1** for shift-after-sum but **-3**
for shift-each-product (after SH). This distinction is relevant
when the real PlayStation instruction order is eventually verified.

`tools/mips_q12_differential.py` assembles actual synthetic MIPS
instruction streams for nine signed-LH pair products and nine
three-term dot products. It executes the streams with the existing
bounded MIPS interpreter, reads all nine signed output SH slots from
mapped memory, and compares them to the independent Python oracle.

A standalone host command reproduces the numeric checks with
fixed-seed generated input matrices and boundary samples:

```sh
python3 -m tools.audit_mips_q12_differential --cases 256 --seed 206
```

The command tested **768 matrix cases** across three schedules, each
with nine output coefficients (**6912 coefficient comparisons**),
all matched. Its JSON shows only per-schedule counts and explicit
`original_gameplay_coefficients_checked: false` and
`playstation_hardware_equivalence_proven: false`. No original game
bytes, private coefficients or captured guest registers are exported.

The newly added 11 reference tests, 10 differential MIPS tests and
six audit/CLI tests bring the locally executable relevant-module
test suite from **200 to 227 passing tests**. Python compilation
(`python -m compileall -q tools tests`) passed as well. All six
new files were verified to match the exact Git blob hashes committed
to GitHub. CTest registrations and the `matrix-audits.yml`
GitHub Actions runner have been extended to run the three new
test files and the deterministic 768-case comparison.

**Proof boundary:** This does NOT establish which arithmetic
schedule, angles or input matrix values the actual `WILDARMS.EXE`
uses. A model matching an independently written oracle for a
synthetic routine does not prove cycle-accurate PS1 hardware
emulation or a working Nintendo Switch native game. Full remote
GitHub Actions success, original-game coefficient equality, and
Switch console execution remain unverified.

## Stage 207 — classify the *executed* matrix arithmetic schedule

The optional exploratory replay now includes
`exploratory_trace.matrix_operation_schedule`, produced by the
new host analyzer `tools/mips_matrix_operation_schedule.py`.
This module interprets **only instructions actually executed** by the
bounded MIPS runner (plus its verified successful LH/LW and SH/SW/SB
memory events), constructing private expression shapes for the
registers and HI/LO values.

For each of the nine fixed 16-bit coefficient slots it reports one
of five safe labels:

- `single_product_sra12` — a signed `MULT → MFLO → SRA 12 → SH`;
- `shift_after_three_products` — three signed `MULT → MFLO`
  products combined with `ADDU` **before** a final `SRA 12`;
- `shift_each_of_three_products` — each of three signed products
  separately receives `SRA 12` before a sequence of `ADDU`s;
- `unclassified` — a final SH executed, but its value is not
  proven to match any of the three recognized instruction structures;
- `not_written` — no longer has a valid complete final SH record.

Unlike mathematical formula guessing, this classifies the **observed
MIPS instruction order**. It explicitly distinguishes `MULT` from
`MULTU` and nontrapping `ADDU` from overflow-trapping `ADD`:
those differing opcodes are never silently called the same known
schedule. It mirrors one-instruction PS1 load delay and preserves
memory-origin shapes through matched byte-level store/reload events.
An overlapping `SB` or `SW` clears a previous SH classification,
and subsequent SH writes replace earlier ones.

The JSON includes aggregate counts, each fixed slot's label and
number of proven signed-MULT terms, whether the bounded guest
execution completed, and these explicit limits:

```json
{
  "synthetic_inputs_only": true,
  "original_builder_schedule_identified": false,
  "bit_exact_ps1_equivalence_proven": false,
  "private_values_emitted": false
}
```

It contains **no opcode words, register values, private addresses,
input angles, trig-table indices, or output coefficients**.
Recognition of a synthetic execution path is not a proof that this
is the original Wild Arms gameplay schedule. A real extracted user
EXE and validated calling state are still necessary.

Example private diagnostic invocation:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-replay --max-steps 4096
```

**Test result:** Seventeen new host analyzer tests cover all three
nine-slot schedules, correct last-write wins behavior, signed versus
unsigned multiplication, ADD versus ADDU, partial byte/word
overwrites, load-delay hazards, corrupted memory events and
fail-closed unrecognized code. Six more synthetic PS-X EXE
integration tests verify end-to-end slot classification, exclusive
`stop_pc` semantics, step-limit uncertainty and privacy-safe
reports. In the locally reconstructed `/mnt/data/wa207` subset,
**250/250 unit tests** and Python `compileall` succeeded. The
three new files were verified to have identical Git blob hashes to
the local copies used in these tests. The suites have been
registered in both host CTest and GitHub Actions.

**Unverified:** full repository CI on the remote GitHub runner,
matrix equivalence with actual `WILDARMS.EXE`, actual PlayStation
input angles and a playable native Nintendo Switch game.

## Stage 208 — original matrix builder opcode evidence, without gameplay-state guesses

The default matrix preflight now includes **static opcode evidence** for
the known Wild Arms builder interval **`0x800B7118–0x800B739C`**,
inclusive. This interval contains `(0x800B739C-0x800B7118)/4+1 = 162`
four-byte instruction words; the **instruction immediately after
`JR $ra` is inspected separately as its return delay slot**.

The new `tools/mips_builder_opcode_evidence.py` inspects only loaded
PS-X EXE machine words. Its result is available in
`builder_opcode_evidence`, including:

- separate static counts for `MULT/MULTU`, `MFLO/MFHI`,
  `SRA 12` versus other right shifts, `ADD` versus `ADDU`,
  `SLL 2`, `ANDI 0x0FFF`, `LH/LHU/LW`, `SH/SB/SW`,
  jumps and other opcodes;
- syntactic `SH` references to nine possible output halfwords
  at offsets `0,2,...,16` relative to `$a1`, including repeated
  write sites and nonmatching `SH` instructions;
- potential local arithmetic shapes for the three schedules
  verified with **synthetic** MIPS data in stages 206–207:
  `single_product_sra12`, `shift_after_three_products`,
  and `shift_each_of_three_products`;
- number of known original `LW` lookup instruction sites
  (`0x800B7140`, `0x800B7168`, `0x800B71A4`,
  `0x800B71CC`, `0x800B7230`, `0x800B7264`)
  whose opcode still matches `LW`;
- whether the chosen end word encodes an exact `JR $ra`,
  whether the next 4-byte return delay slot is mapped, and
  whether that delay slot contains a syntactic matrix `SH`.

Potential arithmetic motifs are strictly **straight-line local**
observations. Conditional branches, jumps, their delay slots, and
unmodeled instructions (especially `COP2`) invalidate accumulated
register/HI/LO symbolic evidence. The recognizer respects the
one-instruction MIPS load delay and does not confuse `MULT`
with `MULTU`, or `ADDU` with overflow-trapping `ADD`.
A matrix `SH` in a branch delay slot is counted separately and
never claimed as a proven local arithmetic schedule.

**Interpretation is intentionally narrow:** a static `SH` word
need not execute; a static table-site `LW` does not establish that
it reads from the trig table at runtime; a local motif is not a
whole-program proof of nine final coefficients. The returned JSON
explicitly has:

```json
{
  "static_words_are_executed": false,
  "original_builder_schedule_identified": false,
  "original_gameplay_coefficients_checked": false,
  "private_values_emitted": false
}
```

Run it on a privately owned extracted executable; no `--explore`
is required for this initial static inventory:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE
```

Inspect `builder_opcode_evidence` in the emitted JSON. The EXE
bytes, opcode words, trig words, private register values and matrix
coefficients are not emitted. Replaying it later is a *separate*
synthetic MIPS probe and is not implied by this static pass.

**Verification:** 19 host tests for the opcode inventory and
six synthetic PS-X EXE integration tests were added, bringing
the relevant locally reconstructed source suite to **275/275
passing tests** (250 earlier + 25 new). Python `compileall`
also passed. The three new files have been uploaded to GitHub
and their Git blob hashes checked against the locally executed
copies. The two new suites are registered in both CTest and
`matrix-audits.yml`. A full remote GitHub CI run, original
`WILDARMS.EXE` results, real coefficient equivalence and
Switch hardware execution are **not verified**.

## Stage 209 — distinguish static builder opcodes from executed guest operations

The stage-208 static code inventory now has a separate **executed-path
correlator** in `tools/mips_builder_execution_evidence.py`. It consumes
the existing bounded MIPS interpreter's *actual* executed-PC sequence
and its successful load/store event streams, then cross-validates
the last successful matrix `SH` in each of the nine halfword slots
against the original-looking `SH rt, offset($a1)` instruction
**at the same executed code site**.

This deliberately separates different strengths of evidence:

- `static_matrix_sh_syntax_site_count`: how many candidate `SH`
  instruction sites exist in the scanned builder interval (including
  a possible `JR $ra` delay-slot `SH`);
- `static_matrix_sh_syntax_sites_executed` versus
  `static_matrix_sh_syntax_sites_not_executed`: which sites the
  synthetic interpreter actually visited, accounting for branches
  and annulled branch-likely delay slots;
- `final_matrix_slots_written_by_sh`: successful last `SH` writes
  to the nine resolved matrix halfwords, irrespective of instruction
  location or base register;
- `final_matrix_slots_verified_against_static_sh_site`: last
  successful writes whose instruction lies within the selected
  builder interval and whose literal `$a1` offset matches the
  actually modified matrix halfword;
- `final_verified_slots_with_recognized_arithmetic_schedule`:
  those validated final sites whose *executed* input expression
  matches a stage-207 signed-`MULT/MFLO/SRA/ADDU` motif;
- `known_trig_lw_sites_executed` and
  `known_trig_lw_sites_with_verified_packed_reads`: number of known
  table lookup instruction sites actually executed, and the subset
  that concretely addressed a complete aligned Q12 entry in memory.

The report's `matrix_slots` array contains nine fixed indices with
booleans for final successful `SH`, matching static code site,
verified `JR $ra` delay-slot write and packed-Q12 lineage, plus
the already recognized arithmetic **label**. It never prints an
original instruction word, actual PC, resolved address, sine/cosine
value, coefficient, or initial game register.

**Important cases:** A skipped branch path may contain a static
`SH` without a successful store. A store through a non-`$a1`
register can still hit the matrix address but does not establish a
match to the syntactic builder site. A real `SH` can later be
overwritten by `SW`, `SB`, or another `SH`: the final coefficient
is then assessed against the last successful write. A valid
`SH` executed after `JR $ra` is counted as a builder return
delay-slot write only if the completed return control transfer is
present in the interpreter trace.

The preflight produces `exploratory_trace.builder_execution_evidence`
only when bounded replay was requested. Purely static analysis
continues to expose `builder_opcode_evidence` without inventing
execution results. Sample command for a user-owned executable:

```sh
python3 -m tools.audit_gp0_matrix_replay_preflight \
  /private/path/WILDARMS.EXE --caller-replay --max-steps 4096
```

This command runs with **synthetic caller registers and stack**, not
captured real gameplay state. The JSON explicitly reports
`runtime_inputs_are_synthetic: true`,
`original_builder_reachability_proven: false`,
`original_gameplay_coefficients_checked: false`, and
`private_values_emitted: false`. Even nine verified writes in a
synthetic fixture do **not** prove the same path is executed by
the PlayStation game.

**Verification:** In the locally reconstructed relevant-module
source tree `/mnt/data/wa209`, all **301/301** Python tests
passed (275 existing plus 19 isolated and 7 synthetic EXE
integration cases). Python `compileall -q tools tests` passed.
The three new modules/test files were verified byte-identical by
Git blob SHA after uploading to GitHub. Test registrations were
added to CTest and `matrix-audits.yml`; remote full CI remains
unverified. No privately owned original `WILDARMS.EXE`, bit-exact
PS1 coefficient values or playable Nintendo Switch native build
were available for validation in this stage.
