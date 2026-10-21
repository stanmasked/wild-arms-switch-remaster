# Stage 310 — exploration journal across two areas and save isolation

This stage adds **host regression coverage** for the existing session-only
journal. It does not change the game world, framebuffer, Switch frontend,
asset inputs, or save schema.

## Integrated runtime scenario

`wa_field_runtime_tests` now checks a deterministic synthetic route:

1. Begin at the cell immediately beside area 0's `!`, press A to
   inspect, then B to record `(area=0,x=4,y=1)`.
2. Enter the pre-existing pending exit at area 0 `(6,5)` and acknowledge
   it with A through the production world-transition handler.
3. Verify the player is in area 1 and the first journal record remains.
4. Release A, inspect the second authored marker and record
   `(area=1,x=4,y=3)` via B. Journal count must be exactly two.
5. Hold L to render both journal rows, with bounded RGBA framebuffer
   guards still intact.
6. Quicksave and quickload the *world*, verifying the two session records
   remain in memory.
7. Construct a fresh runtime and assert its journal starts empty.

The test seeds valid synthetic positions for isolated field-event and
transition checks. It does **not** claim a complete walked route through
both maps or observed NeXium screenshots.

## Save-record invariance

`wa_field_discovery_tests` encodes the same valid world state to the
existing fixed **40-byte v1** save record before and after recording both
event clues. It requires *every byte* — including the existing CRC32 and
world fingerprint — to match exactly and verifies successful decoding.

This explicitly protects the contract that discoveries live only in the
current session; the save codec does not accept a journal and no v1 schema
migration occurs. Recovery of clues after relaunch is intentionally
outside the scope of the current prototype.

## Verification boundary

These tests have been committed to the gameplay Draft PR and registered
within the existing CTest executables. They remain **unconfirmed** until
the exact-head GitHub Actions Host, Matrix, Switch build and experimental
NeXium jobs complete. A passing cross-compile does not prove execution on
physical Nintendo Switch hardware. No original licensed assets were added.
