# Experimental GTE RTPT triple-vertex host reference

Added `include/gte_rtpt_reference.hpp`, `tests/test_gte_rtpt_reference.cpp` and 27th CMake/CTest target. The new RTPT model applies three consecutive calls to the existing RTPS reference and maintains persistent SXY0..2 / SZ0..3 FIFOs. It reports each vertex stage, final IR0, combined stage flags and final SZ3 >> 2.

The tests cover initial FIFO preservation, processing three different depths (100, 200, 300), exact SXY ordering, equivalence to three explicit RTPS reference calls, final-vertex IR0, and persistence of an error flag from the first vertex when subsequent stages succeed.

## Locally confirmed

A complete CMake/GCC host build with existing tests and the new test finished successfully: **27/27 CTest suites passed**. The new implementation was originally staged and tested locally before publication.

## Scope limits

This is a portable experimental reference, not independently hardware-verified PlayStation GTE. Triple-command hardware timing, exact MAC/FLAG edge cases and external hardware register vectors remain unverified. GitHub Actions and a Nintendo Switch runnable game have not been confirmed; no original game assets were uploaded.

Build: `cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure`.
