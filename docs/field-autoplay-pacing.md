# Stage 277 — tested capture pacing for native autoplay

The Stage-275 native autoplay route and host capture are both green in CI.
Stage 276 introduces a PNG comparator, whose CI is still being checked.

Previously the Switch frontend maintained its own timing counters for the
23-step synthetic route. The new portable `include/field_autoplay.hpp`
centralizes timing, so emulator checkpoint captures use a deterministic
policy that host CTest exercises.

- Initial screen and each of the four later checkpoints have a 2500ms
  pause. Intervening logical steps are spaced by 350ms.
- The timer accepts bounded updates of 0–1000ms, consistent with the
  gameplay clock. Longer updates are rejected without consuming the timer.
- A delayed application frame can advance **at most one** logical step.
  Excess time is intentionally discarded at the boundary rather than
  fast-forwarding through several visible checkpoints.
- A completed route freezes at the last checkpoint; restart begins from a
  clean scenario. An invalid game/map state is sticky and cannot continue.
- The frontend uses the same `advance_field_autoplay` update loop tested
  by `wa_field_autoplay_tests`. D-pad and A remain manual controls, X
  starts/restarts autoplay, B cancels, and + exits.

Host tests cover irregular frame partitions, the exact timer boundary,
initial/event hold times, one-step maximum after a 1000ms stall,
invalid-delta nonmutation, fail-closed invalid worlds, deterministic dual
playbacks and final 20-move/2-transition state.

Host commands:

```sh
cmake -S . -B build
cmake --build build --target wa_field_autoplay_tests
ctest --test-dir build -R wa_field_autoplay_tests --output-on-failure
```

This is only static NRO development and host timing verification, **not a
verified launch in NeXium or any other emulator**. No original Wild Arms
game assets, disc data or private keys are shipped.
