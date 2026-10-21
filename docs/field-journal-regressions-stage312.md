# Stage 312 — journal fail-closed revisit and modal inspection-clock regression

This stage fixes two independent host/guest field gameplay edge cases in
PR #34. It is a small code correctness update, not a new renderer or save
format.

## 1. Validate the entire discovery journal before a repeat match

Previously `record_discovery(world, journal, area, x, y)` could return
`PreviouslyRecorded` immediately on the first matching clue, before
checking later journal records. If the later entry was malformed or
duplicated, a repeat lookup silently masked the corrupt state.

The implementation now checks **all active entries** (event tile bounds,
area, and unique keys) first, tracking whether the requested key has
appeared, and reports `PreviouslyRecorded` only after the full validation.
Errors remain non-mutating.

`wa_field_discovery_tests` covers invalid later terrain, a duplicate
entry following the requested matching key, and a corrected two-event
journal that again returns `PreviouslyRecorded`.

## 2. Pause inspection time while L-held modal journal is visible

Previously `advance_field_runtime` decayed the 900ms `FieldInspection`
countdown every simulation frame, even while L suppressed movement and
showed the journal. An inspection could expire behind the modal UI.

The runtime now freezes that countdown **only in manual mode while L is
held**. The native hardware/host frame clock continues advancing
normally; only the ephemeral highlight lifetime is suspended. The UI
resumes the countdown on release and remains unrelated to the v1 save.

`wa_field_runtime_tests` holds L over eight 160ms steps (1280ms),
verifies that the original 900ms inspection remains intact, releases L,
checks the event outline and remaining countdown, records the clue
using B, and subsequently verifies the inspection expires. The
test also checks RGBA framebuffer guard pixels.

## Verification boundary

Code and tests have been committed. GitHub Actions may still be queued;
**no new host, NeXium, or Nintendo Switch console success is asserted**.
The same two synthetic maps are used; original Wild Arms game assets
have not been copied into the repository and the fixed v1 40-byte save
record has not been changed.
