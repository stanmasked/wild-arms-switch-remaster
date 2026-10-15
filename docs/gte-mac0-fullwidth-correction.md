# RTPS MAC0 full-width intermediate correction

## External code comparison

The independent [PCSX ReARMed GTE implementation](https://github.com/notaz/pcsx_rearmed/blob/master/libpcsxcore/gte.c) uses `mac0flags(flags, raw64)` before both screen-coordinate and IR0 limitation. `mac0flags` detects signed 32-bit overflow but **returns the original signed 64-bit value**. Its RTPS path applies `>> 16` to the resulting full-width screen MAC0, or `>> 12` to the depth-cue MAC0, *before* limiting SX/SY or IR0.

Previously, the Wild Arms host reference used `wrap_i32(raw)` before those shifts. This could give a radically incorrect on-screen coordinate when a 64-bit sum overflowed a signed 32-bit register, and could also produce an incorrect IR0 saturation value.

## Corrected modules

- `include/gte_screen_stage.hpp`: SX/SY limiter now reads `floor_shift16(raw)`; MAC0 overflow and screen clip bits are both retained. The stored `mac0_after_y` field stays the signed low 32-bit value.
- `include/gte_depth_cue_stage.hpp`: the IR0 limiter now reads `floor_shift12(raw)`, while exported `mac0` stays signed low 32-bit.
- `tests/test_gte_screen_stage.cpp`: an earlier assertion expected no summary flag for an overflowing screen-coordinate expression, which was only true under the old incorrect wrapping model. The new full-width coordinate also saturates, legitimately setting bit14 and the summary bit31.
- `tests/test_gte_mac0_wide_intermediate.cpp`: positive and negative 32-bit overflow vectors verify SX=+1023, SY=-1024, IR0=4096/0, stored MAC0 wrapping and the associated FLAG bits. These vectors are **derived from the inspected emulator arithmetic** and tested locally, but are not authenticated hardware captures.

## Confirmed local result

Configured and built the full portable C++ project from the staged source tree, then ran all CTest tests with failure output enabled: **25/25 test suites passed**. The initial rebuild exposed the obsolete screen-stage assertion; after updating it to match full-width saturation, the clean 25-suite run passed.

This is a real corrected arithmetic discrepancy against a second open-source GTE implementation, not a proof that the entire experimental GTE reference is hardware bit-exact. Remaining gaps include validating register vectors on real hardware, precise GTE special overflow and FIFO effects, and Nintendo Switch game execution. GitHub Actions CI for these changes has not yet been verified. Original Wild Arms game binaries and textures were not committed.

Local reproduction:

```sh
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
