# Stage 272 — asset-free two-area field transitions

This extends the successfully cross-compiled Stage-270 libnx test app with
a deterministic two-area field world. Both areas are original synthetic
11x7 maps, not extracted or reconstructed Wild Arms data.

- `include/field_world.hpp` owns exactly two areas with map and floor
  entrance coordinates. An exit tile creates a pending Exit state; the player
  cannot move while waiting for acknowledgement.
- **A** pressed after an exit acknowledges the event and transfers to the
  other area's validated entrance, resetting facing to Down. Successful
  move count persists and transfer does *not* count as a move.
- Ordinary event tiles can be acknowledged without changing areas. Held A
  is not an acknowledgement; the controller's existing rising-edge
  semantics are preserved.
- The whole state is validated before each update, including areas,
  spawn points, pending-trigger/clock consistency and the player's current
  position. Malformed world layout is rejected without consuming input.
- The native framebuffer now draws the current area's map with a distinct
  background and status-bar colour so changes are visually apparent.

The new `wa_field_world_tests` target checks event acknowledgement,
two-way exit transitions, movement counters, invalid worlds/states and
deterministic replay including viewport output for both areas.

Build the host test:

```sh
cmake -S . -B build
cmake --build build --target wa_field_world_tests
ctest --test-dir build -R wa_field_world_tests --output-on-failure
```

Build the homebrew binary with devkitPro installed: `make -C switch`.

Passing CI confirms host tests and NRO cross-compilation only. Native
emulator/hardware gameplay, input comfort, timing and screen capture are
not yet verified. No commercial game assets are included.
