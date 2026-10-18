# Stage 265 — asset-free deterministic field-exploration core

This is the first *gameplay-oriented* host-only step following research on
PS1 graphics/GTE/packet provenance and independent-operator infrastructure.

## Included

- New standalone C++20 library `wa_field_core`:
  - Owned row-major grid with dimensions bounded to 1..64 tiles.
  - Explicit allowed tiles: `#` wall, `.` floor, `!` event, `E` exit.
  - Four-direction movement by exactly one tile per update.
  - No ambiguous priority for simultaneous buttons; inputs with two or
    more directions do not move.
  - Face the attempted direction even if a wall blocks movement.
  - Bounds checking, blocked starting-state rejection and malformed-map
    rejection before player state mutation.
  - Entry-trigger semantics: stepping on `!` emits `Event`; stepping on
    `E` emits `Exit`. Waiting or being blocked emits no trigger.
  - A 64-bit successful-move counter with explicit overflow refusal.
- New `wa_field_core_tests` CTest executable: map validation, collision,
  border safety, conflicting inputs, event/exit behavior, overflow,
  invalid player position, state immutability on errors, and scripted
  deterministic replay.
- `wa_field_demo`, a playable host **terminal** demonstration with an
  original ASCII map and W/A/S/D controls. This demonstrates basic field
  traversal without extracting or redistributing original game assets.

## Host usage

```sh
cmake -S . -B build
cmake --build build --target wa_field_core_tests wa_field_demo
ctest --test-dir build -R wa_field_core_tests --output-on-failure
./build/wa_field_demo
```

No copyrighted BIN/CUE, BIOS, sprites or sounds are included. The map and
mechanics are small synthetic examples, **not** a reconstruction of the
original Wild Arms world or game scripting. A successful CTest check is
not evidence of console compatibility.

## Next gameplay work

Build a tile-movement timing layer with configurable stepping cadence and
recorded input trace; connect it to a real Switch libnx NRO frontend; only
after legal/technical access to the user's own image has been verified,
map actual field resources and event scripts to this logic. Follow this
with collision behavior comparison against genuine PS1 gameplay, camera,
save points, rendering and game-state transitions.

The project currently has NO native Switch NRO or verified emulator run,
no original game extraction, no full field engine, no scene streaming,
no combat or native graphics pipeline. Research security PR #33 remains
separate and does not gate this host-only exploratory gameplay module.
