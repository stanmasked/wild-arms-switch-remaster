# RTPS reference integrated into the CMake project

**Verified 2026-10-15.**

The root CMake configuration now registers five host-side tests: core, fixed-point math, vector transform, perspective projection and composite RTPS. A local reconstruction from the repository sources successfully compiled with GCC 14/CMake; **5/5 CTest suites passed**.

## Correction: GTE IR3 is not SZ3

Earlier experimental `rtps_reference` incorrectly passed saturated `IR3` into the depth stage. The revised `Transformed::pre_ir` records the fixed-point shifted transform outputs before IR saturation. `rtps_reference` uses `pre_ir[2]` as its **host approximation** for the SZ3 input and separately preserves the saturated IR register result.

Regression example with identity rotation and translation Z=50000:
- transformed IR3 = 32767 (saturated);
- pre-IR3 depth = 50000;
- projected depth = 50000;
- helper-style shifted return = 12500.

Previously the projected depth was incorrectly capped at 32767. The original Wild Arms helper at `0x800B70E8` reads GTE SZ3 and returns SZ3 arithmetic-shifted right by 2.

This remains **not bit-exact PS1 hardware GTE**: MAC accumulation widths, overflow semantics, dedicated GTE depth pipeline, reciprocal/division, OFX/OFY fractional units, and precise FLAG register behavior are not implemented. The distinction between pre-IR transform Z and SZ3 is a useful structural correction, not hardware equivalence.

Next: add reference vectors and compare against a verified PlayStation GTE implementation, then implement the exact integer pipeline. No original game data committed.
