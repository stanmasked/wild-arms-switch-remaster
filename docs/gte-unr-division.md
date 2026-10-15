# PlayStation GTE UNR divider — portable reference implementation

The GTE performs an approximate perspective divide based on a 257-entry unsigned Newton–Raphson reciprocal table, rather than ordinary floating-point or exact integer division.

The standalone implementation is in `include/gte_unr_division.hpp`, exercised by `tests/test_gte_unr_division.cpp` and registered in root `CMakeLists.txt`.

Primary technical reference: [psx-spx GTE Division Inaccuracy](https://psx-spx.consoledev.net/geometrytransformationenginegte/#gte-division-inaccuracy).

## Verified host-side results

- `H=1, SZ3=1` -> `0x10000`, no overflow.
- `H=2, SZ3=1` -> saturated `0x1FFFF` with divider overflow.
- `H=65535, SZ3=65535` -> `0xFFFF` due to approximate UNR reciprocal (not `0x10000`).
- `H=0, SZ3=0` -> saturated `0x1FFFF`, overflow.
- 65,535 nonzero-denominator cases checked for zero numerator and output/overflow boundary rules.

Standalone host binary compiled using GCC C++20 with `-Wall -Wextra -Werror -pedantic` and passed. This code is *not* original PlayStation game data.

## Limits

These tests establish agreement with the published divider algorithm and its documented boundary cases, **not** hardware-verified exactness. The return flag is only the perspective divider overflow condition (normally contributes FLAG bit17 and summary bit31). It does not emulate the entire GTE FLAG register.

The earlier `project_reference` and `rtps_reference` functions still use their own approximate projection algorithm. This new implementation is deliberately separate; applying it to the full RTPS path requires additional work on screen-offset fixed-point units, pipeline stages, and overflow propagation.

A successful full repository CTest run or GitHub Actions run has not been independently verified for this latest commit. The standalone UNR tests were executed locally.

## Reproduce

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```
