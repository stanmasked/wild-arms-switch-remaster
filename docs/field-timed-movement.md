# Stage 266 — deterministic, timed field movement (host reference)

This change extends Stage 265's synthetic C++20 field core without any
original Wild Arms data or Nintendo Switch binaries.

`include/field_timing.hpp` adds an integer-millisecond movement clock that
calls the existing `step()` engine. The caller supplies an explicit
`delta_ms` and a sampled cardinal `Input` (no wall-clock access or floating
point). The default cadence is 160 ms per attempted tile, configurable
within 40–1000 ms. A call with more than 1000 ms of elapsed time is
**rejected**, not clamped, to make dropped time explicit. Callers can split
long periods into smaller, individually validated calls.

- Holding one direction accumulates time; switching direction or releasing
  keys discards partial cadence. Simultaneous directions are rejected without
  mutation, including without consuming elapsed time.
- Every completed cadence calls the existing map collision and entry-trigger
  logic. Even a large valid update cannot skip an event or map exit.
- Events and exits **pause** the clock immediately and discard unused elapsed
  time. The owner must handle the event and call `acknowledge_trigger()`
  before resuming. The pause is intentional: this is not yet a scripting or
  location-transition system.
- With unchanged input and no trigger, equivalent partitions of elapsed time
  produce the same player/clock state. Frame partition invariance is *not*
  asserted across event/exit acknowledgements because these are intentional
  gameplay boundaries.
- Clock configuration, accumulator invariants, bad map/player states and
  excessive frame deltas are checked before state mutation. Elapsed timing
  does not bypass the existing successful-move overflow protection.

Host regression tests for accumulation, release, direction changes,
collisions, input errors, partition invariance, events, exits and counter
overflow are included in the existing `wa_field_core_tests` target.

Run locally:

```sh
cmake -S . -B build
cmake --build build --target wa_field_core_tests
ctest --test-dir build -R wa_field_core_tests --output-on-failure
```

This remains an **asset-free host prototype**: no native Switch NRO,
graphics frontend, original map parsing, story script, encounter system,
combat, audio or emulator run is claimed. The terminal demo still uses
single-key steps; integrating the timing layer into a real frame-driven
frontend is a subsequent task. Research/security PR #33 remains separate.
