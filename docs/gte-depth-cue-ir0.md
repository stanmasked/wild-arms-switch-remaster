# Standalone GTE depth-cue stage (MAC0 / IR0)

The PlayStation RTPS screen projection is followed by a depth-cue calculation:

```
MAC0 = DQB + (perspective_quotient * DQA)
IR0  = clamp(arithmetic_shift_right(MAC0,12), 0, 4096)
```

Source for the documented hardware formula and FLAG assignments: [psx-spx GTE specifications](https://psx-spx.consoledev.net/geometrytransformationenginegte/).

Implemented in `include/gte_depth_cue_stage.hpp` using signed 16-bit DQA, signed 32-bit DQB, unsigned Q16 UNR quotient, 64-bit temporary arithmetic, detection of MAC0 positive/negative signed 32-bit overflow (FLAG bits16/15), explicit low-32-bit wrap, and IR0 saturation (FLAG bit12). These bits alone do **not** set summary bit31. This is a **standalone subset**, not a full RTPS emulator.

Regression cases in `tests/test_gte_depth_cue_stage.cpp` cover positive and negative DQA, zero input, DQB-only input, saturation at 4096 and just above, positive/negative MAC0 overflow, and negative arithmetic shifting.

## Verified locally

A fresh CMake regeneration and GCC build in the local full project succeeded. All **17/17 CTest test suites passed**, including the new suite `wa_gte_depth_cue_stage_tests`.

One preliminary assertion wrongly expected IR0 saturation for negative DQA when the quotient was zero; correcting the test input to a nonzero quotient fixed that test. The final committed tests use this corrected input.

## Next validations

Integrate the new `DepthCueStage` into a separate RTPS comparison route without overwriting existing baselines. Import **independent hardware/emulator output vectors** and perform differential tests on all output registers and FLAG. Passing current modeled tests does not prove hardware fidelity. Original PlayStation game assets were not uploaded. Native Nintendo Switch build and CI status have not been confirmed for this change.

Rebuild via `cmake -S . -B build && cmake --build build -j4 && ctest --test-dir build --output-on-failure`.
