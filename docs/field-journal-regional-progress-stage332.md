# Stage 332 — regional discovery progress in the field journal

The Stage 331 F/B glyph fix was committed as `44507c22` and its
exact-head CI was queued at the start of this stage. This stage adds
a player-facing overview, not a change to the snapshot codec.

## Regional discovery counts

In the free upper-right header area of the held-L journal, show
regional completion beside the existing overall `CLUES x/2` count:

- `AREA 0 0/1` → `AREA 0 1/1` when the first event is recorded.
- `AREA 1 0/1` → `AREA 1 1/1` when the second event is recorded.

These values are **derived directly** from the already validated
journal ledger and the actual authored `!` tiles of each region,
not hardcoded in the production renderer or written to save files.
Repeated B collection never increments progress. Neither the
narrative two-line notes nor the full 16-entry/2-column list shifts.
Only the manual journal view changes; no autoplay or reference-scene
pixels, movement, NRO inputs or 40-byte v1 save format are altered.

## Verification

- C++ host regression verifies 0/1+0/1, then 1/1+0/1, idempotent
  rediscovery, 1/1+1/1, and full-ledger corruption with transactional
  no-write guarantees and framebuffer stride guards.
- An existing real-controller two-area tour confirms both 1/1
  summaries on the L overlay after collecting both clues.
- The **independent** NeXium Xvfb journal-oracle and synthetic test
  fixtures now require both area lines at native x=660, y=116/140
  inside the existing complete 672×560 panel RGB comparison. A new
  negative synthetic test mutates an area count while preserving
  total clue count, journal border and narrative text.

Any prior successful NeXium run applies only to its exact earlier
commit. Do not claim new regional counters visually confirmed in
the guest until this stage's corresponding GitHub Actions run passes.
The maps are asset-free synthetic test worlds, not original Wild Arms
content or real Nintendo Switch hardware verification.
