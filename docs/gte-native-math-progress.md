# GTE fixed-point C++ groundwork

The repo now contains `include/gte_math.hpp` and a host-only test executable, `wa_gte_math_tests`.

## Implemented and host-tested

- Signed fixed-point floor shift by 12 (scale 4096), including negative inputs.
- Intermediate register bounds for signed IR (-32768..32767) and LM-clamped IR (0..32767).
- Depth saturation primitive (0..65535).
- Screen-coordinate clamping (-1024..1023) and packing into a 32-bit SXY word.

These are **independent mathematical building blocks**, *not* a functioning PlayStation GTE interpreter or complete RTPS implementation. The clamp functions return values only; they **do not** yet set the associated GTE saturation flags. The exact GTE MAC accumulation widths, MVMVA/RTPS operation order, edge cases, fixed-point projection division, FLAG bits and per-stage rounding require further work.

## Source evidence

Verified the actual user-owned Wild Arms (USA) executable helper at `0x800B70E8` a second time directly from its raw MODE2/Form1 image; the 11-word signature contains COP2 `RTPS` (sf=1, lm=0). See `docs/gte-rtps-helper.md`. The current GTE math functions have **not** been validated against hardware/existing-game runtime output.

## Tests

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

Locally verified: both `wa_core_tests` and `wa_gte_math_tests` passed using GCC/CMake/CTest. A successful GitHub Actions run or native Switch `.nro` build has **not** been independently verified.

The next milestone is to recover the caller's GTE matrix and projection setup and implement a reference-tested RTPS subset. No game assets or source image are checked in.
