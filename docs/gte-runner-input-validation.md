# GTE host runner input validation

## Defect fixed

Previously `tests/gte_reference_runner.cpp` read 22 decimal integers as signed 64-bit values and immediately narrowed them to register widths with C++ casts. A direct caller could bypass `tools/compare_gte_rtps_vectors.py` and silently turn an invalid value such as matrix coefficient 65536 into 0 or translation 4294967296 into 0. Such inputs invalidate any differential results.

The runner now **validates all 22 fields before conversion** and exits with status **2** on malformed input. Matrix coefficients (9), vertex (3), and DQA accept signed 16-bit integers. Translation (3), OFX/OFY, and DQB accept signed 32-bit integers. H is unsigned 16-bit. sf/lm must be exactly 0/1. Exactly 22 whitespace-separated integers are required; missing fields, trailing numeric tokens, trailing junk, and 64-bit extraction overflow are rejected. Valid input still emits the existing 11-register output format unchanged.

## Verified locally

The test driver `tests/check_gte_runner_input.py` exercises the **compiled C++ runner** directly across ten scenarios, including 16/32-bit overflow, negative H, invalid sf/lm, missing/extra tokens, malformed trailing input and legal boundary values.

Configured the local full host project using CMake, built with GCC C++20 and ran all CTest suites. Result: **24/24 passing**, including the new executable-level suite `wa_gte_runner_input_contract`. The public `JaCzekanski/ps1-tests` repository's `gte-fuzz/main.c` was checked and implements fuzzer emission, but the expected `gte-fuzz/psx.log` was not available in the inspected repository path, so **no independent hardware snapshot was imported**.

## Limitations

Boundary tests only validate the command-line interface, not PlayStation GTE mathematical accuracy. Hardware fidelity, CI status, a playable Switch build, and game assets integration remain unverified. No original Wild Arms assets were uploaded.

Run: `cmake -S . -B build && cmake --build build -j4 && ctest --test-dir build --output-on-failure`.
