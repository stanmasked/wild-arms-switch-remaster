# Stage 211 — private PS1 matrix numeric reference comparison

This host tool compares nine signed 16-bit matrix coefficients against an **independently supplied reference**. It does not include or distribute original game assets.

## Run locally

```sh
python3 -m tools.audit_ps1_matrix_reference --exe /private/WILDARMS.EXE \
  --reference /private/ps1-matrix-capture.json
```

Expected private JSON schema (placeholders are **not** a valid capture):

```json
{
  "schema": "wild-arms-ps1-matrix-reference-v1",
  "source": "external_ps1_capture_claim",
  "exe_sha256": "<64 lowercase hex characters of full EXE SHA-256>",
  "entry_pc": "0x800b7118",
  "stop_pc": "0x80077988",
  "matrix_address": "0x80110000",
  "gpr": ["<all 32 unsigned 32-bit GPR values, numbered 0-31>"],
  "hi": "0x00000000",
  "lo": "0x00000000",
  "pending_load": null,
  "in_branch_delay_slot": false,
  "max_steps": 4096,
  "memory_segments": [{"address": "0x80000000", "data_hex": "<private RAM bytes in hex>"}],
  "expected_matrix_s16": [0,0,0,0,0,0,0,0,0]
}
```

The sample addresses and zeros are illustrative only. An actual PS1 capture must supply the debugger's **exact instruction-boundary state**: full GPRs, HI/LO, entry PC, RAM/stack/Q12 data referenced by the builder, real matrix output pointer, return/stop PC *after* the final executed SH and JR delay slot, and nine observed **signed** coefficients from that same original-game run. SHA-256 must refer to the precise extracted PS-X EXE before RAM overlay. No missing register or RAM byte is silently populated with synthetic data. Register 0 must equal zero.

`memory_segments` are hexadecimal snapshots of writable guest RAM. A segment can cover all 2 MiB PS1 RAM and overlap or straddle the load-image boundary; the verifier overlays EXE RAM bytes and maps the rest. Segments cannot overlap each other. Total explicit snapshot bytes must not exceed 4 MiB. Matrix buffer must be mapped; `entry_pc` must lie in the image. The source value `external_ps1_capture_claim` is **an unverified declaration**, not an authenticated PS1 observation; use `synthetic` for generated fixtures.

The tool first validates the EXE hash, then runs a bounded MIPS interpreter with the **supplied** state. It checks that execution completed at the **supplied stop PC** and that each of nine final matrix halfwords was written by `SH` (later overlapping SB/SW invalidates it). Only then does it compare nine signed coefficients. The JSON reports the number of matches and mismatching **slot indices**, never guest addresses, registers, original bytes, or coefficient values. Exit code: 0 for 9 matches, 1 for mismatch/incomplete guest run, 2 for invalid input (generic safe JSON error). Keep all captured assets outside GitHub and outside shared logs.

## Limitations

The interpreter is **not** a cycle-exact PS1 emulator: it omits GTE, DMA, interrupts, many CPU corner cases, RAM mirroring and **runtime self-modifying code**. The captured RAM may overlay initial code bytes, but subsequent code writes cannot modify its instruction stream. Matching a user-supplied reference does **not** independently establish hardware provenance, genuine Wild Arms gameplay input, original PS1 equivalence, or a working native Switch port. Report fields `external_ps1_capture_authenticity_independently_verified`, `original_playstation_hardware_equivalence_proven`, `guest_code_mutation_modeled`, `native_switch_port_proven`, and `private_values_emitted` remain false.

Stage 211 adds 31 synthetic tests, including independent Q12 signed-multiply-oracle comparisons, incomplete and overwritten matrix slots, mismatches, SHA checks, invalid/partial memory, executable-memory overlays, entire RAM segments spanning code, and private CLI behavior. No original Wild Arms executable or captured PS1 state is included.

## Stage 213 capture migration

External reference claims must explicitly declare the two pipeline
fields `pending_load` and `in_branch_delay_slot` (see
`docs/ps1-debugger-capture-pack.md`). An absent field is never
treated as a proven empty pipeline for an external capture. Legacy
**synthetic** fixtures may still omit them and default to no pending
load for backward-compatible host tests.

`pending_load` is either `null` or an object containing exactly
`{"gpr": 8, "value_u32": "0x00001000"}`-shaped fields with the true
pending destination and result. Captured GPRs retain the **old**
value before this load has retired. Branch-delay-slot entry is
not yet supported: `in_branch_delay_slot: true` refuses comparison.
Unknown pipeline state must be recaptured at a safe boundary, not
silently guessed.

The comparator exposes only
`initial_load_pipeline_state_explicit` and
`initial_pending_load_applied` booleans; it does not include the
pending target or value in its public summary.

## Stage 214 optional verified JR-return boundary

A reference JSON may now contain `"require_completed_jr_ra": true`
(default: false for backward-compatible synthetic testing). When enabled,
a simple nine-of-nine SH value match is insufficient: the bounded guest
must reach `stop_pc` by **completing `JR $ra`**, including successful
execution of its delay-slot instruction, and must have no pending load
left at that stop.

The safe numerical report provides:

- `strict_jr_ra_return_required`
- `return_boundary.guest_stopped_at_expected_pc`
- `return_boundary.last_completed_transfer_is_jr_ra_to_stop`
- `return_boundary.jr_ra_delay_slot_executed_last`
- `return_boundary.no_pending_delayed_load_at_stop`
- `return_boundary.verified_complete_jr_ra_return`

An incomplete or incorrect return prevents
`coefficient_comparison_performed` and
`matches_supplied_nine_coefficients` from becoming true in strict
mode. These are only booleans; they do not reveal code addresses,
registers or numerical matrix contents. The external capture's
authenticity still cannot be established by this mechanism.

## Stage 215 — optional complete final CPU-state reference

The private JSON may include `"require_final_cpu_state": true`,
together with an `"expected_final_cpu_state"` object containing
**exactly** `gpr` (all 32 unsigned words), `hi`, `lo`,
`pending_load` (null or destination/result object), and
`in_branch_delay_slot: false`. Do not duplicate the PC: the
existing `stop_pc` defines the post-return boundary.
All register contents must come from the **after** capture, not
from the initial register state or the emulator's predicted state.

When the strict option is true, missing or partial final state
is rejected before guest replay. If an optional state object is
present but malformed it is also rejected. If the guest does not
actually reach `stop_pc`, the CPU comparison is withheld rather
than issuing speculative register mismatches.

The report retains
`matches_supplied_nine_coefficients` for numerical matrix agreement,
and adds `matches_complete_reference` for the final decision.
The latter also requires CPU state agreement when requested.
`final_cpu_state` is `null` if no after-register state was supplied;
otherwise it provides only mismatch **GPR numbers**, matching GPR
count and booleans for HI, LO and pending-load equality. The
private state itself is never included in printed JSON. The
CLI uses `matches_complete_reference` for its exit status.

Use `--require-final-cpu-state --require-jr-return --compare`
in the packaging tool when both authentic stop and post-return
register state are available. These comparisons validate only
consistency with **supplied** reference data; PS1 hardware origin
and Nintendo Switch native execution remain unverified.

## Stage 216 — optional full after-RAM block-hash reference

The private reference JSON can include:

```json
{
  "require_final_memory_state": true,
  "expected_final_memory_state": {
    "address": 2147483648,
    "size": 2097152,
    "block_size": 4096,
    "block_sha256": ["<one 64-character lowercase SHA-256 per block>"],
    "expected_changed_bytes_outside_matrix": 0
  }
}
```

These illustrative numbers are **not** a valid reference: a
2-MiB export requires exactly **512 real block digests**. Use
`tools.audit_ps1_capture_pack --require-final-memory-state`
to derive this object privately from *actual* equal-length before
and after raw RAM exports rather than generating it by hand.
The packed format stores digests, not the after-RAM bytes. The
initial `memory_segments` must still provide the entire before
RAM range; unmapped bytes are not assumed to be zero.

The verifier compares exact **after-RAM contents** in the selected
guest virtual interval in 4096-byte blocks. Its public
`final_memory_state` report includes only
`comparison_performed`, `matches_reference`,
`checked_block_count`, `mismatching_block_indices`,
counts of changed bytes **outside the 18 matrix bytes**, and a
change-count equality boolean. Raw bytes, addresses and SHA-256
values stay private. No report of mismatching blocks is emitted
if the guest fails to reach the stop PC.

An absent reference is permitted for legacy synthetic tests
unless `require_final_memory_state` is explicitly true.
Malformed or incomplete supplied reference data always fails
validation, even when strict mode is off. With strict mode on,
`matches_complete_reference` and the CLI exit code require
full-RAM equality **in addition to** the nine coefficient check
and any enabled CPU/JR requirements.

This checks only **net resulting RAM bytes**: same-value stores,
transient writes that are later undone, unmodeled peripherals and
DMA cannot be inferred from snapshots. No real PS1 hardware
capture has been independently authenticated by this feature.

## Stage 217 — optional independent full SB/SH/SW event reference

A private reference can include `"require_store_sequence": true`
(default false) and `"expected_store_sequence"`:

```json
{
  "require_store_sequence": true,
  "expected_store_sequence": {
    "schema": "wild-arms-ps1-store-sequence-v1",
    "events": [
      {"pc": "0x80010004", "address": "0x80110000", "width": 2}
    ]
  }
}
```

This is an *illustrative synthetic* event, not an original-game trace.
Record all successfully executed CPU `SB` (width 1), `SH` (width 2)
and `SW` (width 4) with instruction PCs and destination addresses
from a **separate instruction trace** of the same PS1 run. Event order
and duplicate records matter; do not infer these events from RAM
snapshots. Widths and addresses must be aligned; the store list is
bounded to 100,000 events.

The MIPS interpreter now retains an internal `store_accesses` event
for every successful CPU store, including the PC, resolved address,
width and source GPR number. It still records the older
`store_addresses` array. The comparator checks trace consistency
and compares the first three fields to the private debugger event
log in exact order. No synthetic guessed log is ever inserted.

If `require_store_sequence` is enabled without
`expected_store_sequence`, fixture validation fails. A supplied
malformed optional log also fails validation. In strict mode, a
mismatch prevents `matches_complete_reference` even if nine
coefficients, final CPU, return boundary and final RAM all match.

The safe `store_sequence` result exposes only counts, an event-width
histogram, and at most 32 **mismatching event indices** with a
truncation flag. Raw addresses, PCs, register or memory values are
not emitted. A guest that did not stop at the required PC has no
published mismatch indices. A file claiming to originate from
external PS1 hardware is **not** independently authenticated.

## Stage 218 — independent full store-value reference

A private snapshot may additionally set
`"require_store_values": true` and supply
`"expected_store_values"`:

```json
{
  "require_store_values": true,
  "expected_store_values": {
    "schema": "wild-arms-ps1-store-values-v1",
    "events": [
      {"pc": "0x80010004", "address": "0x80110000",
       "width": 2, "value_u32": "0x00001000"}
    ]
  }
}
```

The data above is a **synthetic placeholder**, not an original
PlayStation capture. The private debugger must record every
successfully completed CPU store, including identical-value
writes and temporary writes subsequently restored. The written
`value_u32` is strictly limited to the low bits represented by
the store width: 0–255 for `SB`, 0–65535 for `SH`, and
0–4294967295 for `SW`. Larger or malformed values are
rejected, not truncated silently during reference decoding.
All store events must be in execution order and aligned by width.

The interpreter privately retains `store_value_accesses`
as `(pc, address, width, rt, actual_low_bits)`, alongside
the backward-compatible `store_addresses` and
`store_accesses`. The evaluator cross-checks their consistency
before comparing the ordered reference. If both the legacy
`expected_store_sequence` and the value-bearing reference
are present, their PC/address/width sequences must be
identical or the input is rejected.

With `require_store_values` enabled, all observed values,
sites and event counts must match before
`matches_complete_reference` can be true. A missing
required log or malformed optional log fails closed.
`matches_supplied_nine_coefficients` retains its separate
nine-halfword meaning. The public `store_values` report
contains *only* counts and capped mismatch indices; it
never reveals values or guest addresses.

Original PS1 debugger provenance and hardware equivalence
cannot be independently proven by this synthetic verifier.

## Stage 219 — independent intermediate arithmetic-event reference

The private snapshot may additionally include
**require_arithmetic_events: true** and a full
**expected_arithmetic_events** object in the following form:

    {
      "require_arithmetic_events": true,
      "expected_arithmetic_events": {
        "schema": "wild-arms-ps1-arithmetic-events-v1",
        "events": [
          {
            "pc": "0x80010000",
            "kind": "mult",
            "result_u32": "0x00200000",
            "secondary_u32": "0x00000000"
          }
        ]
      }
    }

This is **only illustrative synthetic data**, not a PS1 capture.
The exact ordered list must be exported independently from the
original game's debugger. It includes all successfully executed
MULT/MULTU, MFHI/MFLO, SRA/SRAV and ADD/ADDU results. For signed
or unsigned multiplication, result_u32 denotes **LO** and
secondary_u32 denotes **HI**; for the other instruction kinds
secondary_u32 must be null. Result values must be valid unsigned
32-bit words and PCs must be aligned.

When require_arithmetic_events is true, the fixture is rejected
if expected_arithmetic_events is absent. A malformed optional
log is also rejected. With the strict option, all arithmetic
events must match by **executed PC, operation kind, primary value
and secondary HI value** for matches_complete_reference to
become true, even if the nine matrix values already match.
A non-strict optional reference produces diagnostics without
altering the overall result.

The printed arithmetic_events summary contains counts and
bounded mismatching **event indices**, never raw values or PCs.
Only the private owner-restricted snapshot contains complete
numeric reference data. Capture authenticity is not attested.

## Stage 220 — candidate arithmetic mismatch-to-matrix slot map

A validated independent *expected_arithmetic_events* section
automatically enables an **additional diagnostic field** named
*arithmetic_matrix_attribution*. It does not alter existing
reference input fields or the strict arithmetic-event option.

For each of nine matrix slot indices 0–8, the result lists at
most 32 **candidate** mismatching arithmetic event indices
whose observed dataflow reaches that final successful SH.
Primary 32-bit mismatches are kept separate from multiplication
HI-half mismatches. Additional safe fields list candidate
affected slots and mismatch events without a dependency on
any final matrix slot.

Attribution is withheld when the arithmetic reference and
the executed event stream have different numbers or orders
of PC/operation-kind pairs, when the guest replay is incomplete,
or when the bounded dataflow cannot retain all dependencies.
No guest PC, original numerical coefficient, arithmetic
result, HI/LO value, register or RAM byte is returned.

This is **conservative structural dependency**, not proof
that an incorrect intermediate event numerically caused
a wrong matrix coefficient. Algebraic cancellation and
unmodeled external inputs remain possible. The report always
identifies this boundary with
*proven_numeric_causation: false*. Without an independently
recorded original PS1 event trace the field is null.


## Stage 221 — independent LO and HI mismatch accounting

For a single aligned `MULT` or `MULTU` reference event, **both**
`result_u32` (LO) and `secondary_u32` (HI) can disagree with the
replayed MIPS result. The arithmetic comparison now checks the two halves
independently: the **same event index** may appear in
`result_value_mismatch_indices` and `secondary_result_mismatch_indices`.
The top-level `mismatching_event_indices` list remains unique,
`matching_event_count` is calculated from unique incorrect events, and
all three mismatch-index lists retain their 32-entry cap.

When an optional private reference is supplied, the existing Stage 220
dependency report continues to keep primary and HI-half candidates separate
for the last successful SH write to each matrix slot. An event can be a
candidate for different slots through LO and HI simultaneously, but this
does **not** prove numeric causation. A PC/kind alignment error still
prevents numeric classification and any slot attribution.

Regression coverage includes one multiply with both halves incorrect,
more than 32 dual-half mismatches, site mismatch precedence, independent
LO-versus-HI matrix destinations, and the complete synthetic reference
comparison. These tests do **not** authenticate real PS1 captures or
demonstrate Switch runtime compatibility. Private numeric reference data
must stay outside the repository.
