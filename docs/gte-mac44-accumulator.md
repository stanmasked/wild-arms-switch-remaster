# Incremental signed 44-bit GTE MAC accumulator

Added standalone host C++20 components:

- `include/gte_mac44_accumulate.hpp`: signed 44-bit wrapping on each add with sticky positive/negative overflow markers; isolated three-row, three-column integer matrix accumulator.
- `tests/test_gte_mac44_accumulate.cpp`: boundary, consecutive opposite overflow, ordinary identity transform, and large translation test cases.
- Root `CMakeLists.txt` registers the thirteenth CTest suite.

## Confirmed local result

A fresh host CMake/GCC build of the reconstructed project succeeded and **13/13 CTest suites passed**. Initial test expectations for two consecutive operations were corrected after compiling: the first addition at the maximum signed 44-bit value rolls over to the minimum; subtracting one then overflows negatively to the maximum, so **both sticky overflow markers** are expected.

The portable helper `wrap_signed44` explicitly masks and sign-extends 44 bits without implementation-defined signed narrowing. Inputs to `mac44_add` must have sums representable in int64_t, which the configured transform operands satisfy.

## Not yet claimed

- This stage has **not yet been integrated** into `rtps_mac_reference()`; that existing implementation remains available for comparison.
- The correct original GTE RTPS per-operation order, exceptional flags, special IR3/depth FIFO handling, and complete MAC/FLAG hardware equivalence remain to be checked with independent reference vectors.
- Passing host CTest does not imply a successful GitHub Actions run or Nintendo Switch build.

No original Wild Arms images, game executable or proprietary assets have been uploaded.

Reproduce:
```sh
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
