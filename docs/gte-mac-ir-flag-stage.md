# GTE MAC1–MAC3 and IR1–IR3 standalone stage

A new C++20 header `include/gte_mac_stage.hpp` models **a single accumulator-to-intermediate stage**, for signed raw inputs supplied by the caller. This code is independent of game assets and is not a complete PlayStation GTE / RTPS model.

Source of flag assignments and 44-bit signed bounds: [psx-spx PlayStation Specifications — GTE Saturation](https://psx-spx.consoledev.net/psx-spx.pdf).

## Implemented

- Signed 44-bit accumulator positive/negative bounds: [-2^43, 2^43-1].
- Overflow detection: positive bits 30/29/28; negative bits 27/26/25.
- Optional arithmetic division by 4096 (sf=1), then explicitly defined low-32-bit wrapping of each MAC value.
- Signed IR saturation to [-32768,32767] (lm=0), or [0,32767] (lm=1), with bits 24/23/22.
- FLAG bit31 summary according to the documented mask, including the special case that **IR3 bit22 alone does not set bit31**.

## Confirmed local checks

An actual CMake configuration, GCC C++20 build, and full local CTest run returned **11/11 suites passed**, including the new `wa_gte_mac_stage_tests`. Tests cover IR1 clipping, IR3-only clipping and bit31, positive/negative overflow, 44-bit boundaries, 32-bit MAC wrapping, lm=1 negative clipping and negative fixed-point rounding.

## Limits

The stage accepts **already accumulated** signed values. It does not reconstruct the exact GTE matrix multiplication order, 44-bit wrapping during individual multiply-adds, MAC-to-IR timing, RTPS IR3 special behavior, screen/depth FIFO, IR0 or complete FLAG side effects. Accordingly, this is a tested host-side arithmetic component, **not a claim of bit-exact hardware equivalence**.

The existing `gte_rtps_screen_reference.hpp` has **not yet** been rewired to this new stage, deliberately keeping stable comparison baselines.

GitHub Actions and native Nintendo Switch builds are not verified; proprietary original Wild Arms resources remain outside the GitHub repository.

Reproduce:
```sh
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
