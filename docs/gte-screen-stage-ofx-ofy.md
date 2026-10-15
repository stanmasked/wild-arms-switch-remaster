# GTE screen stage (OFX/OFY, MAC0, SX/SY)

A new independent C++20 component, `include/gte_screen_stage.hpp`, models the GTE screen coordinate stage using 16.16 fixed-point OFX and OFY values, the UNR Q16 quotient and signed IR1/IR2 values.

Reference sources:
- https://psx-spx.consoledev.net/psx-spx.pdf (GTE saturation and FLAG bit assignments)
- https://github.com/notaz/pcsx_rearmed/blob/master/libpcsxcore/gte.c (RTPS screen coordinate expression, overflow and saturation)

## Implemented behavior

1. Compute wide signed `OFX + IR1*quotient`, similarly for Y.
2. Detect signed 32-bit MAC0 overflow and negative overflow as FLAG bits 16 and 15.
3. Wrap low 32 bits to signed MAC0; arithmetic shift right by 16 with explicit, portable negative rounding.
4. Saturate SX/SY to [-1024,1023], setting bits 14 and 13.
5. Preserve perspective-divider overflow bit17, and calculate the summary bit31 for the subset modeled.
6. Return packed SXY2 and final MAC0 value after Y calculation.

The helper deliberately accepts *signed 16-bit* IR values and full signed 32-bit OFX/OFY in Q16. Unlike the earlier host-only `gte_projection_unr.hpp`, it does **not** treat offsets as whole pixels.

## Verified

A fresh local GCC/CMake build from the project sources passed **all 9/9 CTest test suites**, including the new `wa_gte_screen_stage_tests`. Test cases include fractional and negative screen offsets, signed right-shift, UNR fractional projection, coordinate saturation, divider overflow and independent MAC0 wrap behavior.

During test development, the first assumption that huge IR*quotient would merely saturate was disproved by actual 32-bit wrap. The regression tests were corrected to model wrapping and clipping separately.

## Not yet verified

- Hardware-confirmed output vectors from an original PlayStation, including exact FLAG behavior under concurrent overflow.
- Full RTPS MAC1..3 pipeline, IR0, FIFO side effects and depth color-cue.
- Integration of this screen stage into the composite `rtps_unr_reference()`.
- GitHub Actions and Nintendo Switch build/run.

This code is a **partial GTE screen-stage reference**, not a full hardware-exact emulator and not a runnable Wild Arms port. No original game assets were uploaded.
