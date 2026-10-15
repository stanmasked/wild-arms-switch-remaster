# RTPS with incremental 44-bit MAC — host reference

Added `include/gte_rtps_mac44_reference.hpp` as a *separate* comparison path and `tests/test_gte_rtps_mac44_reference.cpp`. The previous `rtps_mac_reference()` remains unchanged.

The new variant composes:
1. `matrix44_accumulate`: sequential translation + three multiply-adds per row, 44-bit sign extension/wrap after each addition and sticky overflow flags.
2. `mac_ir_from_raw`: Q12 shift, 32-bit MAC representation and IR saturation.
3. Depth calculation from wrapped third accumulator, UNR perspective division and Q16 OFX/OFY screen stage.
4. Aggregated **partial** GTE diagnostic flags and a `SZ3 >> 2` return.

## Confirmed differential result

With translation X = INT32_MAX, first-row matrix elements (32767, -32768, 0) and vertex (32767, 32767, 0), the first multiply-add temporarily crosses the positive 44-bit bound, then the next brings the final sum back into the allowed range.

- **New:** detects sticky MAC1 positive overflow, setting FLAG bit30.
- **Previous:** final-wide-sum-only implementation misses this overflow.
- Both models give the same final value and MAC1 low 32 bits in this case.

A second case tests persistent overflow and sign wrapping, where the new intermediate accumulator becomes negative.

## Build status

Fresh local host CMake configure/build completed. `ctest --output-on-failure` reported **14/14 passing tests**, including the new reference suite. These test expectations are derived from modeled arithmetic, **not independent PlayStation hardware traces**.

## Important remaining gaps

The implementation is **not yet hardware-equivalent RTPS**. Real GTE sequence, depth FIFO, IR3 special saturation, IR0, exact FLAG[31] behavior under complex combinations, MAC0 details, and independent original-hardware reference vectors need further research and testing. The existing C++ header hierarchy is for portability testing, not a full game renderer or Switch executable.

GitHub Actions CI has not been independently confirmed for the latest changes. Original Wild Arms assets are not uploaded.

Reproduce locally:

```sh
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
