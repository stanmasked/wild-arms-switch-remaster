# Stage 313 — transactional manual-state preflight

The Stage 312 journal and inspection changes introduced a shared question:
what happens if the journal is corrupt while the player never presses L?

Before this stage, `advance_field_runtime` preflighted the complete journal
**only** for the modal L journal. In ordinary manual play a damaged ledger
could remain undetected until an attempt to render the journal. The input
code could also encounter an invalid world pending-trigger state during the
modal path without exercising the normal movement validation.

## Runtime change

Every manual frame now preflights **both**:

- `valid_field_snapshot(world, current.manual)`: validates the player,
  map identity, pending event tile, and clock state.
- `valid_discovery_journal(world, current.discoveries)`: checks all active
  records for authored `!` tiles, bounds and unique location keys.

The preflight runs *before* copying/updating the tick accumulator, sampling
movement/inspection input, touching quicksave, or rendering to the RGBA buffer.
A failure returns `RuntimeStatus::InvalidSimulation` and leaves the caller's
runtime and pixel target untouched.

Autoplay remains isolated: it is allowed to ignore a dormant manual
journal, and cancelling autoplay initializes a new valid manual world.

## Regression coverage

`wa_field_runtime_tests` injects one valid event clue followed by a
corrupt second entry and attempts each manual control separately:
D-pad movement, B collection, L journal, X autoplay start, Y quicksave,
and Minus quickload. Every call must fail without advancing ticks,
moving, switching modes, writing a save, or changing a single pixel.
After repairing the entry the test verifies ordinary movement resumes.

A further negative case marks a floor tile as a pending event and opens L:
the preflight must reject this invalid world snapshot before drawing.

This is a host test and not a new original Wild Arms map, a physical Switch
execution, or a change to the version-1 40-byte save record.

## CI boundary

Commit and test registration are confirmed by GitHub repository state.
No claim of passing Stage 313 CI or successful NeXium screenshot replay
is made while the exact-head GitHub Actions workflows are queued.
