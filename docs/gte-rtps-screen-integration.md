# Integrated host RTPS with GTE-style OFX/OFY

Added `include/gte_rtps_screen_reference.hpp` and `tests/test_gte_rtps_screen_reference.cpp`. This separate host comparison path combines 4.12 matrix rotation/translation, pre-IR3 depth preservation, unsigned Newton–Raphson (UNR) perspective division, and the previously tested GTE-style fixed-point screen stage using signed 16.16 OFX/OFY.

The earlier `rtps_unr_reference()` is unchanged, so differences can be isolated.

## Confirmed local checks

A fresh GCC/CMake configure/build and CTest run completed: **10/10 suites passed**, including the new `wa_gte_rtps_screen_reference_tests`.

Regression cases:
- Identity transform with vertex (100,-50,200), H=100, OFX=320px, OFY=240px projects to (370,215), depth return `SZ3>>2=50`.
- Identical integer screen offsets agree with the earlier host UNR composite on the ordinary scenario.
- Fractional offsets `OFX=1.5px`, `OFY=-0.5px` produce (1,-1) under explicit arithmetic right shift.
- Zero depth triggers UNR division-overflow reporting.
- Translation depth 50000 maintains SZ3=50000 even when IR3 is saturated to 32767; helper-style return = 12500.
- Quantized UNR divider at `H=Z=32767, X=1023` produces SX=1022.

## Important limitations

This is **not** yet bit-exact PlayStation GTE. The implementation uses a reference matrix stage rather than GTE-accurate MAC1–MAC3 widths, per-step truncation/saturation and GTE FLAG semantics. No SZ FIFO, IR0 behavior, color cue or exact GTE control state are integrated. The tests are host-side expected-value checks, not recorded outputs from original console hardware.

No game assets or original executable are committed. The main application and Nintendo Switch build are not complete. GitHub Actions status has not been independently verified for this commit.

## Reproduction

```sh
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
