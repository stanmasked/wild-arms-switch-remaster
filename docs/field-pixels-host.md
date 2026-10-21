# Stage 273 — shared, testable software rasterizer

`include/field_pixels.hpp` now owns the exact asset-free RGBA8888 field
rasterization used by the standalone Switch NRO. The libnx source invokes
`draw_field_pixels` on the linear framebuffer; no separate renderer can
silently diverge from the host implementation.

The rendering contract:
- 1280×720, tile pitch 64 pixels, standard RGBA8888 byte packing.
- Validates writable target geometry, bounded stride, frame metadata,
  terrain types, area number and **exactly one traversable player** before
  modifying any pixel. Pointer validity/buffer ownership remain the
  responsibility of the caller.
- Fully clears the visible raster and paints deterministic terrain tiles,
  player facing marker, area backgrounds and event-pause status bar.
- Never writes into row padding or beyond the requested 720 visible rows.
- Rejects malformed frames without partially painting the prior image.

`wa_field_pixels_tests` checks fixed terrain/player pixels, both area
colours, paused and facing variants, out-of-bounds row guards, unchanged
output on validation errors, and duplicate-run determinism.

Host commands:

```sh
cmake -S . -B build
cmake --build build --target wa_field_pixels_tests
ctest --test-dir build -R wa_field_pixels_tests --output-on-failure
```

Building with `make -C switch` exercises the same raster header with
libnx Framebuffer and PadState. This does **not** yet prove the NRO runs
on a Switch console or supported emulator; no gameplay screenshot from a
native device was captured. Original Wild Arms assets remain private.
