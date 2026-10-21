# Stage 314 — manual L journal movement-cadence isolation

## Problem

With an unfinished 160ms movement period (for example, 80ms already
carried while Right was held), opening the read-only L journal prevented
movement but preserved that half-paid period. A Right hold after releasing
L could therefore move the sprite prematurely.

## Fix

On every manual L journal frame, after validated/transactional input
preflight, reset only the *movement clock's transient directional*
`carry_ms` and `held` fields. Do not change the authoritative monotonic
frame-tick clock, saved world, inventory/journal state or inspection UI.
Pending event clock states already require those fields to be neutral.

This is an explicit modal-input policy: a direction pressed after closing
the journal must earn its full movement cadence rather than replaying an
incomplete directional period from before the journal opened.

## Host regression

`test_journal_releases_old_partial_movement_cadence` first pays 80ms of
the 160ms Right-step interval, holds L+Right for seven 80ms updates, and
verifies that neither position nor movement-clock debt changes. After
releasing L, Right must spend another two 80ms updates to move from x1 to
x2. RGBA framebuffer stride/tail guards are checked.

The test is registered through the existing `wa_field_runtime_tests`
CTest executable. Both the host and native Switch renderer use the
shared runtime header. The original v1 save codec, synthetic maps, and
game assets are unchanged.

**CI caveat:** repository changes and test registration do not equal
a passing CTest/NRO build or a real NeXium observation. Exact-head
GitHub Actions results are required for that claim.
