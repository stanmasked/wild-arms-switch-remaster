# Integrated experimental RTPS with MAC/IR stage

Implemented `include/gte_rtps_mac_reference.hpp` and `tests/test_gte_rtps_mac_reference.cpp`. This *separate host reference* combines a 4.12 integer rotation/translation matrix, standalone MAC1–3/IR1–3 saturation and partial FLAG logic, UNR perspective divide, fixed-point OFX/OFY screen stage and the return value `SZ3 >> 2` observed in Wild Arms' original GTE helper.

## Verification

A clean local CMake configure/build succeeded with the host compiler, and **12 of 12 registered CTest suites passed**, including `wa_gte_rtps_mac_reference_tests`.

Coverage includes identity transform, comparison with the pre-existing screen reference, translation Z=50000 (IR3 saturates at 32767 while SZ3 remains 50000), depth 0 or negative, IR1 saturation, and expected subset of FLAG bits.

## Critical limits

This code is **not a cycle-accurate or bit-accurate PS1 GTE RTPS implementation**. It computes a complete wide matrix sum before the standalone MAC stage. Actual GTE hardware requires per-operation 44-bit accumulator overflow and wrap behavior, plus special IR3 semantics, exact SZ FIFO updates, IR0 calculation, additional FLAG rules and reliable hardware-derived reference vectors. The combination of independently tested pieces is **not** proof of full hardware compatibility.

This is a native portable C++20 analysis artifact and does **not** produce a Nintendo Switch executable or playable Wild Arms. Original game resources have not been uploaded.

GitHub Actions CI has not been verified for this change.

## Reproduce

```sh
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
