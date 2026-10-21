# Stage 325 — discovered clue checkmarks on manual field tiles

## Verified baseline

[NeXium #39333181342](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/39333181342)
successfully completed on `e00ab69c`. Its real guest
L-journal reinspection oracle now passes after Stage 324 moved the
CLUE NOTED caption away from NeXium's statistics HUD. Host Core,
native Switch NRO build and host PNG reference workflows also passed
for that original commit.

## Player-facing addition

An `!` event that has been discovered by an intentional A inspection
and subsequent B collection now has a small original blue square
with a white check mark **on its tile** during ordinary manual walking.
This distinguishes explored clues from unseen clues at a glance.

- Only entries in the validated in-session discovery journal are
  annotated, keyed by **area, x, y**.
- Outside the active area or outside the camera viewport: do not draw.
- On a player-occupied event tile: do not overwrite the player sprite.
- Holding L draws the existing modal journal instead; scripted
  autoplay **never** receives badges. Its five host/guest reference
  scenes remain unaffected.
- All journal entries and framebuffer bounds are validated before
  writing any pixels; invalid ledgers fail without mutation.
- No map, movement controls, clues, save operations or 40-byte version
  1 world-save bytes are changed.

The badge itself is 18×18 native RGBA8888 pixels at offset (25,25)
inside a 64×64 event tile, with a white check glyph. It uses only
locally authored flat colors and geometric raster primitives.

## Tests and proof limits

`test_discovered_marker_is_read_only_area_specific_and_bounded`
verifies unchanged undiscovered tiles, area-specific badge placement,
the full-ledger corruption rejection, no player overdraw and stride
guards. `test_discovery_marker_only_during_manual_exploration`
exercises a real A/B clue collection via controller input, then L
modal behavior, and autoplay isolation.

A new exact-head Host Core, Switch NRO and NeXium test suite is
needed. This commit cannot retroactively inherit the old emulator
pass. Experimental NeXium is not physical console testing.

## Actual guest visual coverage

The existing NeXium L-journal screenshots already include an A/B
sequence before/after collecting one area-0 marker. Its *previous*
Stage 324 guest screenshot at (569,225) was gold both before and
after collecting: no badge feature existed then.

Stage 325 extends the **independent observed NeXium screenshot audit**
with an exact full 18×18 projected RGB oracle for the new badge.
`02_at_marker` must still show the uncollected gold event tile;
`06_one_closed`, `08_revisited_noted` and `10_revisit_expired`
must display the complete blue-and-white checkmark. Synthetic
negative fixtures reject absent badges and even one changed visible
badge pixel. This increases the audit to 14 independent checks.

This is not a claim of a passing guest test: an exact-head NeXium
run must execute after this addition.
