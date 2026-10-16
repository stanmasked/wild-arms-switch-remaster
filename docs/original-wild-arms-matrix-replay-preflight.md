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
