# Stage 322 — instant recognition of previously recorded clues

The Stage 321 exact-head CI confirms the Stage 320 prototype: 125/125
host CTests, the NRO build, and experimental NeXium guest visual audits,
including five pixel-perfect projected scene comparisons and a real
L-held journal interaction, completed successfully.

## Player-facing improvement

Previously the A inspection of an already-discovered event initially
said **EVENT AHEAD**. Only another B press switched the caption to
**CLUE NOTED**, even though the journal already contained that marker.

On a new A inspection, manual field runtime now looks up the adjacent
`!` marker in the validated session ledger using **area + x + y**.
If already recorded, the blue **CLUE NOTED** caption appears immediately.
New, unrecorded event markers still display yellow **EVENT AHEAD**.
The inspect action remains read-only and does not award clues.

## Tests

- `test_read_only_clue_membership_respects_area_and_count` checks
  area-aware lookup, empty and full journals, the count bound and that
  membership never changes entries.
- `test_reinspection_immediately_indicates_recorded_clue` first
  inspects and records the authored area-0 event, waits for the old
  caption to expire, and inspects again. A alone must render the blue
  `CLUE NOTED` caption without changing the ledger. A further B press
  reports a harmless repeated clue, and framebuffer guards stay intact.

No original game assets or additional save fields are added. The
40-byte v1 world save and the existing journal panel remain unchanged.

**Verification boundary:** Stage 321's NeXium proof applies to its
original commit `f726f4ab`; the Stage 322 change requires new
exact-head CI before a successful guest run can be claimed.
