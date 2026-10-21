# Stage 278 — drift-free hardware tick conversion

The Stage-277 NRO used integer division of system counter ticks per frame.
At 60 fps this truncated approximately 16.667 milliseconds down to 16 for
each update, permanently discarding fractional milliseconds and making the
game clock run up to several percent slow.

The platform-neutral `include/field_frame_ticks.hpp` now carries the
fractional millisecond numerator across frames and yields an exact 1000ms
after sixty equally spaced ticks of a 19.2 MHz Nintendo Switch timer. It
avoids floating point and prevents unsigned underflow on clock resets.

- Frequency must be in the range 1000 to 1,000,000,000 ticks per second.
- A clock counter reset returns zero elapsed gameplay time and synchronizes
  the reference tick.
- An applet pause/stall **longer than one second** yields zero gameplay time
  and clears its fractional remainder. This intentionally prevents catch-up
  movement when returning from HOME/suspend.
- Individual updates are bounded to 0–1000ms for the existing gameplay
  and autoplay contracts. Elapsed time exactly equal to one second is
  permitted.
- Invalid clock state is rejected without mutation.
- The same adapter will be compiled in the devkitPro NRO; no new platform
  runtime API is required beyond `armGetSystemTickFreq` and
  `armGetSystemTick`.

Six regression groups cover 60Hz accumulation, noninteger tick
frequencies with frame partitioning, long pauses, counter resets,
uint64 boundaries, invalid states and zero/exact-second updates.

Host commands:

```sh
cmake -S . -B build
cmake --build build --target wa_field_frame_ticks_tests
ctest --test-dir build -R wa_field_frame_ticks_tests --output-on-failure
```

Successful host tests and cross-compilation do **not** establish runtime
performance in NeXium or on Nintendo Switch hardware. All map data and
graphics remain independently invented synthetic examples, with no
original Wild Arms resources in public source control.
