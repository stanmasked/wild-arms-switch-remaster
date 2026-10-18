# Stage 267 — bounded viewport render snapshot (host-only)

This layer prepares a renderer-facing description of the synthetic field
without choosing a graphics API or including any copyrighted resources.

`include/field_view.hpp` provides:

- `build_view(frame, map, player, viewport)`: immutable gameplay inputs,
  transactional frame output (errors preserve the previous frame).
- Camera following in integer tile units, clamped at the edges when a map is
  at least as large as the viewport. Smaller maps are centered with explicit
  empty-space padding.
- Fixed-size `RenderFrame` with at most 32 × 32 cells, no dynamic allocations
  in the snapshot code. Each cell keeps its *terrain* and *player occupancy*
  distinct so an event/exit cannot disappear from the render data when the
  character stands on it.
- Explicit `CellKind` values Outside/Wall/Floor/Event/Exit, plus facing.
  Future libnx or other frontends can map these into their own tile sprites
  and player animation. This layer creates **no pixels** and cannot itself
  render to Switch.
- `glyph_for` translates that snapshot to ASCII as an optional host adapter.
  The terminal demo now displays a moving 9 × 5 viewport and facing marker
  instead of printing the entire map directly.

Six new host regression groups cover camera clamping, event/exit terrain,
small maps and padding, malformed maps/positions/directions/viewports,
maximum viewport capacity and deterministic replay.

Verification command:

```sh
cmake -S . -B build
cmake --build build --target wa_field_core_tests wa_field_demo
ctest --test-dir build -R wa_field_core_tests --output-on-failure
./build/wa_field_demo
```

This is still only a host-side scene-description prototype. It has no
native Switch NRO, GPU renderer, scene streaming, original Wild Arms map
extraction, combat, audio, controller driver or emulator validation. No
copyrighted game assets or BIOS are included.
