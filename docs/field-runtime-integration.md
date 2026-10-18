# Stage 279 — unified field runtime (host and libnx)

The Native Switch field main loop used to independently wire the hardware
timer, controller, autoplay, map view, and RGBA rasterizer. These were unit
tested, but the exact orchestration was not host-testable.

`include/field_runtime.hpp` now implements that orchestration once.
The libnx entrypoint is reduced to configuring Framebuffer/PadState,
sampling its monotonic counter, and passing the data to
`advance_field_runtime`. The same function is used by
`wa_field_runtime_tests` on an ordinary host compiler.

Controls and semantics:
- D-pad and stick/A for manual movement and event/exit acknowledgement.
- X (rising edge) starts/restarts scripted autoplay; B cancels back to
  the synthetic starting map; + still leaves the program.
- Clock counter remainders are carried from frame to frame, and a pause
  longer than one second does not catch up game time.
- Each scenario checkpoint runs through exactly the same rendering
  pipeline as manual play, using 1280x720 RGBA pixels.
- Invalid map/timer/target is rejected before changing gameplay or
  touching pixel memory. No libnx services are used by the host tests.

Three integration test groups cover:
1. Sixty nominal 60Hz frames, manual movement, event pause, fresh A
   acknowledgement, held confirm and counter-suspend time skip.
2. Failed input/world/clock preflight leaving the framebuffer and
   monotonic clock untouched, plus stride padding sentinels.
3. Dual deterministic autoplay render streams, five checkpoints,
   two transitions, 20 moves, final image equality, cancel and restart.

This is not a substitute for running the compiled NRO in NeXium.
Host results prove deterministic behavior of the shared core only.
The project uses original synthetic maps and does not distribute
Wild Arms disc, BIOS, maps, sprites or audio assets.

Run:
```sh
cmake -S . -B build
cmake --build build --target wa_field_runtime_tests
ctest --test-dir build -R wa_field_runtime_tests --output-on-failure
make -C switch
```
