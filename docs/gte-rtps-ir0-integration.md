# RTPS + depth cue IR0: host reference integration

Added `include/gte_rtps_ir0_reference.hpp` and `tests/test_gte_rtps_ir0_reference.cpp` without modifying the earlier comparison routes.

The new host-side helper calls `rtps_mac44_depth_reference()` to compute the existing per-add MAC44 matrix stage, IR1–IR3, SZ3, UNR ratio and screen position. It then passes the UNR Q16 quotient to `depth_cue_stage()` with DQA and DQB and merges its FLAG bits. The helper's `SZ3 >> 2` return and screen outputs are preserved.

Verified test cases include:
- identity transform and vertex (100,-50,200) with H=100, OFX=320, OFY=240 yields screen (370,215), SZ3=200 and return 50;
- DQA=1, DQB=0 with quotient 0x8000 computes MAC0=32768 and IR0=8 without changing screen XY;
- IR0 saturation at 4096 sets FLAG bit12 alone, not summary bit31;
- negative depth-cue input clips IR0 to zero;
- positive MAC0 overflow sets bit16 but does not by itself set bit31;
- translated depth 50000 is distinct from saturated IR3=32767.

A locally staged CMake/GCC rebuild including the previous 17 tests and the new integration suite passed **18/18 CTest suites**. The staged test includes additional cases; the published test checks the same essential behavior. GitHub Actions and Switch compilation were **not verified**.

Important: this is NOT an independently hardware-tested, cycle-accurate or complete PS1 GTE. It lacks full FIFO effects, precise stage sequencing and verified console output fixtures. Proprietary Wild Arms game data remain outside GitHub.

Reproduce with `cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure`.
