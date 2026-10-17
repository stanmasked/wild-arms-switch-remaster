# Stage 239 — joined claimed MIPS branch, delayed load and address evidence

Stages 237 and 238 deliberately separated two imperfect sources of
evidence. The first checks privately supplied PC/address sequences
against a user-owned executable; the second models a **claimed**
register state, delayed `LW` result and `BEQ/BNE` decision. Passing each
separately did **not** establish that both inputs described the same
instruction sequence.

`tools/audit_record_pipeline_coupling.py` introduces a stricter
**opt-in** comparison. It takes one executable-hash-bound stage-236/237
capture and per-observation initial GPR/load-result claims. From the
**exact already claimed PC list**, it retrieves the corresponding
instruction words from that EXE and builds a stage-238 model input.
The capture cannot supply replacement opcode words or different
branch PC lists for the second checker.

## Guardrails

- Every `(site, record_index)` in the EXE-bound capture must have exactly
  one accompanying pipeline sample. Missing, duplicated and foreign
  samples are refused before a partial report is emitted.
- Each index must supply an initial `v0` equal to the statically known
  pre-final-shift coefficient `677 × record_index`. The first listed
  global `LW v1,0x2c3c(v1)` must claim to load the *same* global base
  recorded in the stage-237 address observation. An initial `v1`
  register value must identify a valid nonwrapping and aligned global
  pointer slot address for the model; it is **not** independently
  authenticated as real game RAM.
- The same execution-PC sequence must contain the original `LW`,
  following independent `SLL`, supported `BEQ/BNE` branches with
  literal NOP delay slots, and one terminal direct `LW`. Exactly the
  two corresponding per-PC loaded values must be supplied. Other
  loads, noncanonical PC keys, unsupported control flow or external
  addresses are rejected.
- The stage-238 model evaluates each branch predicate against the
  provided initial/loaded GPR values with one-instruction load delay,
  while the stage-237 validator independently checks encoded branch
  targets, PC order, EXE hash, claimed addresses and cross-site deltas.
- The **final effective address computed by the pipeline model must
  match the same private address used in the EXE-bound observation**.
  This is implemented as a new optional *private comparison*, and does
  not alter stage-238 standalone defaults or publish the address.

The joined result is **counts and booleans only**. Stage 237's
`claimed_data_consistent_with_checked_in_code` must be true, and
every claimed site/index sample must pass the separate delayed-load
model for the joint `joined_private_claims_consistent` flag to be
true. A structurally valid but numerically contradictory claim exits
**1**; malformed or unsupported input exits **2** with a generic
`invalid_private_input` status; complete claimed consistency exits **0**.
No private PC, address, opcode, register value, EXE SHA, or original-game
bytes are included in standard JSON output.

## Private input

Use the original stage-236
`wild-arms-ps1-executed-record-access-claims-v1` capture structure
unchanged, nested in `access_claim`. Add `pipeline_samples` with one
entry for each indexed observation. For illustration **only**, an entry
looks like:

```json
{
  "schema": "wild-arms-ps1-coupled-branch-load-claims-v1",
  "access_claim": {"schema": "wild-arms-ps1-executed-record-access-claims-v1"},
  "pipeline_samples": [
    {
      "site": "site_1",
      "record_index": 0,
      "initial_gprs_u32": {
        "2": "0x00000000",
        "3": "0x80130000"
      },
      "lw_results_u32": {
        "0x8006d27c": "0x80120000",
        "0x8006d298": "0x00000021"
      }
    }
  ]
}
```

This **illustrative fragment is intentionally not valid by itself**:
the real `access_claim` requires EXE hash, source, 2–3 function
sites, 3–32 samples per site, and full actual claimed-PC sequences.
All sample values above are synthetic and are **not evidence from an
original game copy**. Stage-239's strict supported subset requires
forward ordinary `BEQ/BNE` and the original one-instruction `LW`
gap; it cannot validate branchless observations, tail stores,
exception paths, memory operations inside branch slots, or multiple
additional loads.

Execute privately on user-owned local media:

```sh
python3 -m tools.audit_record_pipeline_coupling \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/joined-branch-load-claim.json
```

Do not put EXE contents, user-owned disc images, RAM snapshots, raw
debugger traces, or private joint claims in GitHub. There is a
256 KiB private JSON input limit; the existing image/inventory
validation is retained.

## Important non-claims

A numerically matching pair of **user-supplied** register snapshots
and effective addresses does not prove that a debugger actually
captured either one, that the EXE matches a particular original-game
release, or that the observed branching corresponds to any real
hardware run. Stage 238 intentionally lacks full R3000A cycle,
exception, cache and register collision handling.

The checked-in opcode-derived multiplier **2708** remains an index
coefficient, **not** a verified in-game record size. The older
364-byte assumption is still unsupported, and the separate 88-byte
initializer remains unrelated. Nothing here establishes a native
Nintendo Switch game build.

Synthetic regressions cover multi-site positive correlation,
contradictory loaded base, wrong pre-shift index, wrong predicate
register, cross-site mismatches, missing/duplicate/foreign site
samples, out-of-window PCs, private input sanitation, and
backward-compatibility of both older independent checkers.
